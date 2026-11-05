<?php
/**
 * Plugin Name: BM Pomocnik (importery)
 * Description: Pola własne w REST dla importerów danych ze stron do SportsPressa (zalążek pluginu z etapu E3). Wgrywany jako mu-plugin.
 *
 * Pola (wszystkie tekstowe, widoczne w REST w polu "meta"):
 *  - bm_source, bm_source_id: źródło i identyfikator rekordu w źródle (drużyna, zawodnik, mecz); po nich importer dopasowuje rekordy,
 *  - bm_source_hash: skrót treści ze źródła; importer pomija zapis, gdy skrót się nie zmienił,
 *  - bm_logo (drużyna): ścieżka logo względem folderu logo modułu, np. "garbarnia/Garbarnia.png"; bm_name14 (drużyna): nazwa do 14 znaków dla nakładek, bm_short_name (drużyna): skrót 3-znakowy,
 *  - bm_first_name, bm_last_name (zawodnik): imię i nazwisko osobno (tytuł w WP to jedno pole); edytowalne w panelu WP (Pola własne).
 * Trasa bm/v1/event/<id>/clear (POST, wymaga prawa edycji): czyści wynik, skład i statystyki zawodników meczu (zapis przez REST SportsPressa
 * tylko scala dane, więc importer czyści mecz przed aktualizacją).
 * Mecz dodatkowo: bm_live, bm_locked (flagi, jak w pluginie testowym), a REST wystawia minuty zdarzeń (sp_timeline) w polu "timeline".
 *
 * W8a: stan i wynik meczu z modułu transmisji. Trasa bm/v1/event/<id>/state (POST, wymaga prawa edycji meczu), ciało JSON:
 *   seq (liczba całkowita >= 1, rosnąca per mecz; zapis z seq <= zapisanemu jest potwierdzany bez zmian: idempotencja),
 *   state ("nierozpoczety" | "trwa" | "zakonczony"), home, away (wynik: na żywo przy "trwa", końcowy przy "zakonczony"),
 *   opcjonalnie pen_home, pen_away (wynik konkursu rzutów karnych, tylko przy "zakonczony"; zwycięzcę liczy WP: wynik, a przy remisie konkurs).
 * Zwycięzca: bm_winner ("home" | "away" | ""), bm_winner_team (id drużyny w WP), bm_pen_home, bm_pen_away (tylko przy "zakonczony").
 * Pola: bm_state, bm_live_score ("g:o", tylko gdy trwa), bm_seq, bm_result_source ("modul", gdy natywny wynik wpisał moduł), bm_result_hash,
 *   bm_live (zgodność: prawda tylko przy "trwa"), bm_locked (organizator blokuje zapis z modułu: 409).
 * Pierwszeństwo danych: bm_decyduje (flaga meczu; prawda = stan i wynik wpisuje użytkownik modułu, źródło prawdy ich nie nadpisuje). Ustawia ją moduł
 *   w polu "decyduje" (true/false) trasy stanu: automatycznie przy wyborze meczu do transmisji albo jawnie z zakładki MECZE. Importer pomija taki mecz i tylko raportuje różnicę.
 *   bm_locked zostaje twardą blokadą zapisu z modułu (409). Trasa bm/v1/event/<id>/source-state (POST, ciało: state, home, away) służy importerowi do zapisu
 *   stanu i wyniku NA ŻYWO ze źródła (nie rusza bm_seq ani natywnego wyniku); odpowiada 409 dla meczu z bm_decyduje albo bm_locked.
 * bm_zrodlo_brak (flaga meczu, ustawiana przez import): mecz zniknął ze źródła albo został w nim odwołany. Mecz nigdy nie jest usuwany; tabela (W8b) wyłącza
 *   z tabeli live mecz niezakończony z tą flagą, a zakończony zostaje w tabeli z ostrzeżeniem.
 * W8b: GET bm/v1/table?league&season&mode=final|live: tabela ligowa na żądanie (wirtualna, baza bez zmian), opis przy funkcji bm_table_compute.
 * Natywny wynik SportsPressa (sp_results) i status "publish" są ustawiane WYŁĄCZNIE przy "zakonczony". Po zamknięciu meczu wygrywa WP:
 *   wynik, którego moduł nie wpisał albo który zmieniono po zapisie z modułu, nie jest nadpisywany (409 bm_wp_result).
 */
if (!defined('ABSPATH')) exit;

add_action('init', function () {
	foreach (['sp_team', 'sp_player', 'sp_event'] as $pt) {
		add_post_type_support($pt, 'custom-fields');
		foreach (['bm_source', 'bm_source_id', 'bm_source_hash'] as $k) {
			register_post_meta($pt, $k, ['show_in_rest' => true, 'single' => true, 'type' => 'string']);
		}
	}
	register_post_meta('sp_team', 'bm_logo', ['show_in_rest' => true, 'single' => true, 'type' => 'string']);
	register_post_meta('sp_team', 'bm_name14', ['show_in_rest' => true, 'single' => true, 'type' => 'string']);
	register_post_meta('sp_team', 'bm_short_name', ['show_in_rest' => true, 'single' => true, 'type' => 'string']);
	foreach (['bm_first_name', 'bm_last_name'] as $k) {
		register_post_meta('sp_player', $k, ['show_in_rest' => true, 'single' => true, 'type' => 'string']);
	}
	foreach (['bm_live', 'bm_locked', 'bm_decyduje', 'bm_zrodlo_brak'] as $k) {
		register_post_meta('sp_event', $k, ['show_in_rest' => true, 'single' => true, 'type' => 'boolean']);
	}
	foreach (['bm_state', 'bm_live_score', 'bm_result_source', 'bm_result_hash', 'bm_winner'] as $k) {
		register_post_meta('sp_event', $k, ['show_in_rest' => true, 'single' => true, 'type' => 'string']);
	}
	foreach (['bm_seq', 'bm_pen_home', 'bm_pen_away', 'bm_winner_team'] as $k) {
		register_post_meta('sp_event', $k, ['show_in_rest' => true, 'single' => true, 'type' => 'integer']);
	}
});

const BM_STANY = ['nierozpoczety', 'trwa', 'zakonczony'];

/** Drużyny meczu w kolejności gospodarz, gość (pole sp_team; 0 = wolne miejsce w drabince). */
function bm_event_teams($id) {
	return array_map('intval', (array) get_post_meta($id, 'sp_team', false));
}

/** Natywny wynik meczu [gospodarz, gość] albo null, gdy mecz nie ma wyniku w obu drużynach. */
function bm_native_score($id, $teams) {
	$res = get_post_meta($id, 'sp_results', true);
	if (!is_array($res) || count($teams) < 2) return null;
	$out = [];
	foreach ([$teams[0], $teams[1]] as $t) {
		$g = isset($res[$t]['goals']) ? $res[$t]['goals'] : '';
		if ($g === '' || !is_numeric($g)) return null;
		$out[] = (int) $g;
	}
	return $out;
}

function bm_score_hash($score) {
	return md5($score[0] . ':' . $score[1]);
}

function bm_state_answer($id, $duplicate) {
	$teams = bm_event_teams($id);
	return [
		'ok' => true, 'duplicate' => $duplicate, 'id' => $id, 'seq' => (int) get_post_meta($id, 'bm_seq', true),
		'state' => (string) get_post_meta($id, 'bm_state', true), 'live_score' => (string) get_post_meta($id, 'bm_live_score', true),
		'result' => bm_native_score($id, $teams), 'result_source' => (string) get_post_meta($id, 'bm_result_source', true),
		'decyduje' => (bool) get_post_meta($id, 'bm_decyduje', true),
		'winner' => (string) get_post_meta($id, 'bm_winner', true), 'winner_team' => (int) get_post_meta($id, 'bm_winner_team', true),
		'pen' => [get_post_meta($id, 'bm_pen_home', true) === '' ? null : (int) get_post_meta($id, 'bm_pen_home', true),
		          get_post_meta($id, 'bm_pen_away', true) === '' ? null : (int) get_post_meta($id, 'bm_pen_away', true)],
	];
}

function bm_event_state($req) {
	$id = (int) $req['id'];
	if (get_post_type($id) !== 'sp_event') return new WP_Error('bm_not_event', 'To nie jest mecz', ['status' => 404]);
	$p = $req->get_json_params();
	if (!is_array($p)) $p = [];
	$state = isset($p['state']) ? (string) $p['state'] : '';
	if (!in_array($state, BM_STANY, true)) return new WP_Error('bm_bad_state', 'Nieprawidłowy stan meczu', ['status' => 400]);
	$seq = isset($p['seq']) ? (int) $p['seq'] : 0;
	if ($seq < 1) return new WP_Error('bm_bad_seq', 'Brak numeru zapisu (seq >= 1)', ['status' => 400]);
	$home = (isset($p['home']) && $p['home'] !== '') ? (int) $p['home'] : null;
	$away = (isset($p['away']) && $p['away'] !== '') ? (int) $p['away'] : null;
	if (($home !== null && $home < 0) || ($away !== null && $away < 0)) return new WP_Error('bm_bad_score', 'Wynik nie może być ujemny', ['status' => 400]);
	$pen_home = (isset($p['pen_home']) && $p['pen_home'] !== '') ? (int) $p['pen_home'] : null;
	$pen_away = (isset($p['pen_away']) && $p['pen_away'] !== '') ? (int) $p['pen_away'] : null;
	if (($pen_home === null) !== ($pen_away === null) || ($pen_home !== null && ($pen_home < 0 || $pen_away < 0))) {
		return new WP_Error('bm_bad_pen', 'Wynik konkursu rzutów karnych wymaga obu wartości nieujemnych', ['status' => 400]);
	}

	if (get_post_meta($id, 'bm_locked', true)) return new WP_Error('bm_locked', 'Wynik tego meczu jest zablokowany w WP', ['status' => 409]);
	if ($seq <= (int) get_post_meta($id, 'bm_seq', true)) return bm_state_answer($id, true);
	if (array_key_exists('decyduje', $p)) update_post_meta($id, 'bm_decyduje', $p['decyduje'] ? '1' : '');     // przed regułami zamknięcia: flaga ma sens także przy 409

	$teams = bm_event_teams($id);
	if (count($teams) < 2 || $teams[0] <= 0 || $teams[1] <= 0) return new WP_Error('bm_no_teams', 'Mecz nie ma ustalonych obu drużyn', ['status' => 409]);

	// Po zamknięciu meczu wygrywa WP: wynik wpisany przez organizatora/import albo zmieniony po zapisie z modułu nie jest nadpisywany.
	$native = bm_native_score($id, $teams);
	$source = (string) get_post_meta($id, 'bm_result_source', true);
	$hash = (string) get_post_meta($id, 'bm_result_hash', true);
	$wp_owns = $native !== null && !($source === 'modul' && $hash === bm_score_hash($native));
	$same = $native !== null && $state === 'zakonczony' && $home === $native[0] && $away === $native[1];
	if ($wp_owns && !$same) {
		return new WP_Error('bm_wp_result', 'WP ma inny wynik tego meczu (' . $native[0] . ':' . $native[1] . ')', ['status' => 409, 'wp_result' => $native]);
	}

	if ($state === 'zakonczony') {
		if ($home === null || $away === null) return new WP_Error('bm_bad_score', 'Zakończony mecz wymaga wyniku', ['status' => 400]);
		if (!$wp_owns) {
			$res = get_post_meta($id, 'sp_results', true);
			if (!is_array($res)) $res = [];
			$o = $home > $away ? ['win', 'loss'] : ($home < $away ? ['loss', 'win'] : ['draw', 'draw']);
			foreach ([[$teams[0], $home, $o[0]], [$teams[1], $away, $o[1]]] as $row) {
				$cur = (isset($res[$row[0]]) && is_array($res[$row[0]])) ? $res[$row[0]] : [];
				$res[$row[0]] = array_merge(['firsthalf' => '', 'secondhalf' => ''], $cur, ['goals' => (string) $row[1], 'outcome' => [$row[2]]]);
			}
			update_post_meta($id, 'sp_results', $res);
			update_post_meta($id, 'bm_result_source', 'modul');
			update_post_meta($id, 'bm_result_hash', bm_score_hash([$home, $away]));
			wp_update_post(['ID' => $id, 'post_status' => 'publish']);
		}
		// zwycięzca: wynik meczu, a przy remisie konkurs rzutów karnych; bez rozstrzygnięcia puste
		$zw = '';
		if ($home > $away) $zw = 'home';
		elseif ($away > $home) $zw = 'away';
		elseif ($pen_home !== null && $pen_home !== $pen_away) $zw = $pen_home > $pen_away ? 'home' : 'away';
		update_post_meta($id, 'bm_winner', $zw);
		if ($zw !== '') update_post_meta($id, 'bm_winner_team', $zw === 'home' ? $teams[0] : $teams[1]); else delete_post_meta($id, 'bm_winner_team');
		if ($pen_home !== null) {
			update_post_meta($id, 'bm_pen_home', $pen_home);
			update_post_meta($id, 'bm_pen_away', $pen_away);
		} else {
			delete_post_meta($id, 'bm_pen_home');
			delete_post_meta($id, 'bm_pen_away');
		}
		update_post_meta($id, 'bm_live', '');
		delete_post_meta($id, 'bm_live_score');
	} elseif ($state === 'trwa') {
		if ($source === 'modul') {      // natywny wynik zapisany wcześniej przez moduł nie może zostać w meczu, który znów trwa
			delete_post_meta($id, 'sp_results');
			delete_post_meta($id, 'bm_result_source');
			delete_post_meta($id, 'bm_result_hash');
		}
		foreach (['bm_winner', 'bm_winner_team', 'bm_pen_home', 'bm_pen_away'] as $k) delete_post_meta($id, $k);
		update_post_meta($id, 'bm_live', '1');
		update_post_meta($id, 'bm_live_score', ($home !== null && $away !== null) ? ($home . ':' . $away) : '');
	} else { // nierozpoczety
		if ($source === 'modul') {
			delete_post_meta($id, 'sp_results');
			delete_post_meta($id, 'bm_result_source');
			delete_post_meta($id, 'bm_result_hash');
		}
		foreach (['bm_winner', 'bm_winner_team', 'bm_pen_home', 'bm_pen_away'] as $k) delete_post_meta($id, $k);
		update_post_meta($id, 'bm_live', '');
		delete_post_meta($id, 'bm_live_score');
	}
	update_post_meta($id, 'bm_state', $state);
	update_post_meta($id, 'bm_seq', $seq);
	return bm_state_answer($id, false);
}

/** Stan i wynik NA ŻYWO ze źródła (import): bez numeru zapisu i bez natywnego wyniku; mecz z bm_decyduje albo bm_locked jest odrzucany (409). */
function bm_event_source_state($req) {
	$id = (int) $req['id'];
	if (get_post_type($id) !== 'sp_event') return new WP_Error('bm_not_event', 'To nie jest mecz', ['status' => 404]);
	$p = $req->get_json_params();
	if (!is_array($p)) $p = [];
	$state = isset($p['state']) ? (string) $p['state'] : '';
	if (!in_array($state, ['nierozpoczety', 'trwa', 'zakonczony'], true)) return new WP_Error('bm_bad_state', 'Nieprawidłowy stan meczu', ['status' => 400]);
	if (get_post_meta($id, 'bm_locked', true) || get_post_meta($id, 'bm_decyduje', true)) {
		return new WP_Error('bm_decyduje', 'Stan i wynik tego meczu ustala użytkownik (blokada albo flaga decyduje)', ['status' => 409]);
	}
	$home = (isset($p['home']) && $p['home'] !== '') ? (int) $p['home'] : null;
	$away = (isset($p['away']) && $p['away'] !== '') ? (int) $p['away'] : null;
	if ($state !== 'zakonczony') {      // natywny wynik istnieje tylko dla meczów zakończonych: powrót do „nierozpoczęty”/„trwa” (także z importu) czyści wynik i zwycięzcę
		foreach (['sp_results', 'bm_result_source', 'bm_result_hash', 'bm_winner', 'bm_winner_team', 'bm_pen_home', 'bm_pen_away'] as $k) delete_post_meta($id, $k);
	}
	if ($state === 'trwa') {
		update_post_meta($id, 'bm_live', '1');
		update_post_meta($id, 'bm_live_score', ($home !== null && $away !== null) ? ($home . ':' . $away) : '');
	} else {
		update_post_meta($id, 'bm_live', '');
		delete_post_meta($id, 'bm_live_score');
	}
	update_post_meta($id, 'bm_state', $state);
	return bm_state_answer($id, false);
}

/* ------------------------------------------------------------------------------------------------------------------------------------------------
 * W8b: tabela ligowa NA ŻĄDANIE: GET bm/v1/table?league=<id termu ligi>&season=<id termu sezonu>&mode=final|live[&criteria=<slug kryteriów SAH2H>]
 * Tabela WIRTUALNA: klasa tabeli SportsPressa (z dodatkiem Advanced H2H i kryteriami "t1-nalf": bezpośrednie spotkania przed różnicą bramek ogółem) liczona na
 * identyfikatorze bez wpisu w bazie; metadane tabeli, termy ligi i sezonu oraz wyniki meczów (sp_results) podstawia filtr odczytu NA CZAS JEDNEGO ŻĄDANIA. Baza bez zmian.
 * Reguły jawnego stanu (bm_state): ZAKONCZONY liczy się zawsze (także z flagą bm_zrodlo_brak, z ostrzeżeniem); mecz z natywnym wynikiem bez bm_state to stan niejawny =
 * zakończony (mecze z pełnego importu). NIEROZPOCZĘTY nigdy (także z resztkowym wynikiem natywnym). TRWA: tryb final nigdy, tryb live tylko z niepustym wynikiem na żywo
 * (bm_live_score) i bez flagi bm_zrodlo_brak; wynik na żywo jest podstawiany w pamięci. Wersje pinowane: SportsPress 2.7.31, Advanced H2H 2.2.0 (zależność od wnętrza klas).
 * Pozycja w odpowiedzi = numer wiersza (SAH2H daje drużynom z równymi punktami wspólną pozycję; losowanie poza systemem).
 * Odpowiedź: mode, columns (klucz, nazwa, etykieta), rows, matches_counted, live_matches, warnings (typ, mecz, opis, wplyw), engine, criteria, computed_at.
 * ------------------------------------------------------------------------------------------------------------------------------------------------ */
const BM_TABELA_VID = 900000001;
const BM_TABELA_KOLUMNY = ['p' => 'M', 'w' => 'W', 'd' => 'R', 'l' => 'P', 'f' => 'BZ', 'a' => 'BS', 'gd' => 'RB', 'pts' => 'Pkt', 'wa' => 'WyW'];

/** Czy wynik natywny meczu ma rezultat (outcome) którejkolwiek drużyny: tak liczy SportsPress. */
function bm_table_ma_wynik($res) {
	if (!is_array($res)) return false;
	foreach ($res as $row) if (is_array($row) && !empty($row['outcome'])) return true;
	return false;
}

/** Wynik na żywo "g:o" -> [g, o] albo null. */
function bm_table_live_score($s) {
	return (is_string($s) && preg_match('/^(\d+):(\d+)$/', $s, $m)) ? [(int) $m[1], (int) $m[2]] : null;
}

/** Natywny wynik złożony z wyniku na żywo (tylko w pamięci jednego żądania). */
function bm_table_wynik_z_zywo($teams, $g, $o) {
	$r = $g > $o ? ['win', 'loss'] : ($g < $o ? ['loss', 'win'] : ['draw', 'draw']);
	return [$teams[0] => ['goals' => (string) $g, 'outcome' => [$r[0]]], $teams[1] => ['goals' => (string) $o, 'outcome' => [$r[1]]]];
}

/** Wynik: ['rows','columns','warnings','matches_counted','live_matches','engine'] albo WP_Error. Nic nie zapisuje w bazie. */
function bm_table_compute($league, $season, $mode, $criteria) {
	$lt = get_term($league, 'sp_league');
	$st = get_term($season, 'sp_season');
	if (!($lt instanceof WP_Term) || !($st instanceof WP_Term)) return new WP_Error('bm_no_table', 'Nie ma takiej ligi albo sezonu w WP', ['status' => 404]);
	$team_ids = array_map('intval', get_posts(['post_type' => 'sp_team', 'numberposts' => -1, 'posts_per_page' => -1, 'fields' => 'ids', 'tax_query' => [
		'relation' => 'AND', ['taxonomy' => 'sp_league', 'field' => 'term_id', 'terms' => [$league]], ['taxonomy' => 'sp_season', 'field' => 'term_id', 'terms' => [$season]]]]));
	if (!$team_ids) return new WP_Error('bm_no_table', 'Brak tabeli: liga i sezon nie mają drużyn', ['status' => 404]);
	if (!class_exists('SP_League_Table')) return new WP_Error('bm_no_sportspress', 'SportsPress nie jest aktywny', ['status' => 500]);

	$event_ids = get_posts(['post_type' => 'sp_event', 'post_status' => ['publish', 'future'], 'numberposts' => -1, 'posts_per_page' => -1, 'fields' => 'ids',
		'orderby' => 'ID', 'order' => 'ASC', 'meta_query' => [['key' => 'sp_format', 'value' => ['league'], 'compare' => 'IN']], 'tax_query' => [
			'relation' => 'AND', ['taxonomy' => 'sp_league', 'field' => 'term_id', 'terms' => [$league]], ['taxonomy' => 'sp_season', 'field' => 'term_id', 'terms' => [$season]]]]);

	// W tabeli tylko drużyny, które mają mecz w tej lidze i sezonie (import NALF przypisuje drużynom wszystkie ligi; bez tego dostalibyśmy wiersze z 0 meczów)
	$w_meczach = [];
	foreach ($event_ids as $eid) foreach ((array) get_post_meta($eid, 'sp_team', false) as $t) if ((int) $t > 0) $w_meczach[(int) $t] = true;
	$druzyny_tabeli = array_values(array_filter($team_ids, fn($t) => isset($w_meczach[$t])));
	if (!$druzyny_tabeli) $druzyny_tabeli = $team_ids;      // liga bez żadnych meczów: wszystkie drużyny z termami

	$ov = [];                 // id meczu => wyniki podstawiane zamiast natywnych (pusta tablica = mecz nie liczy się)
	$ostrz = [];
	$liczone = 0; $live = 0;
	$pary = [];
	$nazwa_meczu = function ($id, $teams) {
		$n = array_map(fn($t) => $t ? get_the_title($t) : '?', $teams);
		return ($n[0] ?? '?') . ' - ' . ($n[1] ?? '?');
	};
	$dodaj = function ($typ, $id, $teams, $opis, $wplyw) use (&$ostrz, $nazwa_meczu) {
		$ostrz[] = ['typ' => $typ, 'mecz_id' => $id, 'mecz' => $nazwa_meczu($id, $teams), 'opis' => $opis, 'wplyw' => $wplyw];
	};
	foreach ($event_ids as $id) {
		$teams = array_values(array_map('intval', array_filter((array) get_post_meta($id, 'sp_team', false))));
		$res = get_post_meta($id, 'sp_results', true);
		$ma_wynik = bm_table_ma_wynik($res);
		$stan = (string) get_post_meta($id, 'bm_state', true);
		$flaga = (bool) get_post_meta($id, 'bm_zrodlo_brak', true);
		$zywo = bm_table_live_score((string) get_post_meta($id, 'bm_live_score', true));
		$rodzaj = ($stan === 'zakonczony' || ($stan === '' && $ma_wynik)) ? 'zakonczony' : ($stan === 'trwa' ? 'trwa' : 'nierozpoczety');
		if (count($teams) >= 2 && $teams[0] > 0 && $teams[1] > 0) {
			$pary[$teams[0] . '-' . $teams[1]][] = ['id' => $id, 'liczony' => false];
			foreach (array_slice($teams, 0, 2) as $t) {
				if (!in_array($t, $team_ids, true)) {
					$dodaj('druzyna_spoza_ligi', $id, $teams, 'Drużyna „' . get_the_title($t) . '” nie należy do tej ligi i sezonu; SportsPress liczy ten mecz tylko dla drużyny z ligi.', 'liczony dla drużyny z ligi');
				}
			}
		}
		$liczy = false;
		if ($rodzaj === 'zakonczony') {
			if ($stan === 'zakonczony' && !$ma_wynik) {
				$dodaj('zakonczony_bez_wyniku', $id, $teams, 'Mecz oznaczony jako zakończony nie ma wyniku w WP.', 'nie liczy się do tabeli');
			} else {
				$liczy = true;
				if ($flaga) $dodaj('zniknal_ze_zrodla', $id, $teams, 'Mecz zakończony zniknął ze źródła albo został w nim odwołany (flaga bm_zrodlo_brak).', 'zostaje w tabeli');
			}
		} elseif ($rodzaj === 'nierozpoczety') {
			if ($ma_wynik) {
				$ov[$id] = [];
				$dodaj('wynik_resztkowy', $id, $teams, 'Mecz nierozpoczęty ma wynik natywny (resztka po poprawce stanu).', 'wynik pominięty');
			}
		} else {          // trwa
			if ($ma_wynik) {
				$ov[$id] = [];
				$dodaj('wynik_resztkowy', $id, $teams, 'Mecz trwający ma wynik natywny jak zakończony (resztka po poprawce stanu).', 'wynik pominięty');
			}
			if ($mode === 'live') {
				if ($flaga) {
					$ov[$id] = [];
					$dodaj('zniknal_ze_zrodla', $id, $teams, 'Mecz niezakończony zniknął ze źródła albo został w nim odwołany (flaga bm_zrodlo_brak).', 'wyłączony z tabeli live');
				} elseif ($zywo !== null && count($teams) >= 2 && $teams[0] > 0 && $teams[1] > 0) {
					$ov[$id] = bm_table_wynik_z_zywo($teams, $zywo[0], $zywo[1]);
					$liczy = true; $live++;
				} else {
					$ov[$id] = [];
					$dodaj('trwa_bez_wyniku_na_zywo', $id, $teams, 'Mecz trwa, ale nie ma wyniku na żywo.', 'pominięty w tabeli live');
				}
			} else {
				$ov[$id] = [];
			}
		}
		if ($liczy) { $liczone++; if (count($teams) >= 2 && isset($pary[$teams[0] . '-' . $teams[1]])) $pary[$teams[0] . '-' . $teams[1]][count($pary[$teams[0] . '-' . $teams[1]]) - 1]['liczony'] = true; }
	}
	foreach ($pary as $klucz => $lista) {
		if (count($lista) < 2) continue;
		$ids = array_column($lista, 'id');
		$liczone_kopie = count(array_filter($lista, fn($x) => $x['liczony']));
		[$a, $b] = array_map('intval', explode('-', $klucz));
		$dodaj('duplikat_meczu', $ids[0], [$a, $b], 'Ta sama para gospodarz-gość występuje ' . count($lista) . ' razy (mecze ' . implode(', ', $ids) . ').',
			$liczone_kopie >= 2 ? 'liczona wielokrotnie (' . $liczone_kopie . ' razy)' : 'liczony ' . $liczone_kopie . ' raz');
	}

	$engine = 'SP';
	$klasa = 'SP_League_Table';
	if (class_exists('SAH2H_League_Table') && get_page_by_path($criteria, OBJECT, 'sah2h_criteria')) {
		$klasa = 'SAH2H_League_Table';
		$engine = 'SAH2H';
	} else {
		$ostrz[] = ['typ' => 'konfiguracja', 'mecz_id' => 0, 'mecz' => '', 'opis' => 'Brak dodatku Advanced H2H albo kryteriów „' . $criteria . '”: użyto tabeli SportsPressa bez bezpośrednich spotkań przed różnicą bramek.', 'wplyw' => 'kolejność przy remisie może odbiegać od regulaminu'];
	}

	$f_meta = function ($v, $oid, $key, $single) use (&$ov, $criteria, $druzyny_tabeli) {
		if ($oid == BM_TABELA_VID) {
			if ($key === 'sp_team') return $druzyny_tabeli;       // wybór ręczny: lista drużyn z meczami (get_post_meta(..., false) zwraca listę wartości)
			$map = ['sp_select' => 'manual', 'sp_orderby' => 'default', 'sp_order' => 'ASC', 'sp_event_status' => ['publish', 'future'], 'sp_date' => 0, 'sah2h_criteria' => $criteria];
			return array_key_exists($key, $map) ? [$map[$key]] : $v;
		}
		if ($key === 'sp_results' && isset($ov[$oid])) return [$ov[$oid]];
		return $v;
	};
	$f_terms = function ($terms, $pid, $tax) use ($lt, $st) {
		return $pid == BM_TABELA_VID ? [$tax === 'sp_league' ? $lt : $st] : $terms;
	};
	add_filter('get_post_metadata', $f_meta, 10, 4);
	add_filter('get_the_terms', $f_terms, 10, 3);
	// get_the_terms() kończy się wcześnie, gdy get_post() nie znajdzie wpisu: wirtualny wpis tabeli trafia więc na czas żądania do pamięci podręcznej obiektów
	wp_cache_set(BM_TABELA_VID, (object) ['ID' => BM_TABELA_VID, 'post_type' => 'sp_table', 'post_status' => 'publish', 'post_title' => '', 'filter' => 'raw'], 'posts');
	try {
		$tabela = new $klasa(new WP_Post((object) ['ID' => BM_TABELA_VID, 'post_type' => 'sp_table', 'post_status' => 'publish']));
		if ($klasa === 'SAH2H_League_Table') $tabela->h2h_criteria = $criteria;
		$dane = $tabela->data();
	} finally {
		remove_filter('get_post_metadata', $f_meta, 10);
		remove_filter('get_the_terms', $f_terms, 10);
		wp_cache_delete(BM_TABELA_VID, 'posts');
	}
	unset($dane[0]);                 // wiersz 0 to etykiety kolumn SportsPressa
	$kolumny = [];
	$tytuly = [];
	foreach (get_posts(['post_type' => 'sp_column', 'numberposts' => -1, 'posts_per_page' => -1, 'orderby' => 'menu_order', 'order' => 'ASC', 'post_status' => 'publish']) as $c) $tytuly[$c->post_name] = $c->post_title;
	foreach (BM_TABELA_KOLUMNY as $klucz => $etykieta) {
		if (isset($tytuly[$klucz])) $kolumny[] = ['klucz' => $klucz, 'nazwa' => $tytuly[$klucz], 'etykieta' => $etykieta];
	}
	$wiersze = [];
	$poz = 0;
	foreach ($dane as $team_id => $r) {
		$poz++;
		$tytul = get_the_title($team_id);
		$w = ['pos' => $poz, 'team_id' => (int) $team_id, 'name' => $tytul,
			'name14' => (string) (get_post_meta($team_id, 'bm_name14', true) ?: mb_substr($tytul, 0, 14)),
			'short' => (string) (get_post_meta($team_id, 'bm_short_name', true) ?: mb_strtoupper(mb_substr($tytul, 0, 3)))];
		foreach ($kolumny as $k) $w[$k['klucz']] = isset($r[$k['klucz']]) && is_numeric($r[$k['klucz']]) ? (int) $r[$k['klucz']] : 0;
		$wiersze[] = $w;
	}
	return ['rows' => $wiersze, 'columns' => $kolumny, 'warnings' => $ostrz, 'matches_counted' => $liczone, 'live_matches' => $live, 'engine' => $engine];
}

function bm_table_endpoint($req) {
	$mode = (string) ($req['mode'] ?: 'final');
	if (!in_array($mode, ['final', 'live'], true)) return new WP_Error('bm_bad_mode', 'mode musi być final albo live', ['status' => 400]);
	$league = (int) $req['league'];
	$season = (int) $req['season'];
	if ($league < 1 || $season < 1) return new WP_Error('bm_bad_params', 'Wymagane: league i season (identyfikatory termów)', ['status' => 400]);
	$criteria = (string) ($req['criteria'] ?: get_option('bm_table_criteria', 't1-nalf'));
	$t0 = microtime(true);
	$w = bm_table_compute($league, $season, $mode, sanitize_title($criteria));
	if (is_wp_error($w)) return $w;
	return ['ok' => true, 'mode' => $mode, 'league' => $league, 'season' => $season, 'criteria' => sanitize_title($criteria), 'computed_at' => gmdate('c'),
		'ms' => (int) round((microtime(true) - $t0) * 1000)] + $w;
}

add_action('rest_api_init', function () {
	register_rest_route('bm/v1', '/table', [
		'methods' => 'GET',
		'permission_callback' => fn() => current_user_can('edit_posts'),
		'callback' => 'bm_table_endpoint',
	]);
	register_rest_route('bm/v1', '/event/(?P<id>\d+)/source-state', [
		'methods' => 'POST',
		'permission_callback' => fn($req) => current_user_can('edit_post', (int) $req['id']),
		'callback' => 'bm_event_source_state',
	]);
	register_rest_route('bm/v1', '/event/(?P<id>\d+)/state', [
		'methods' => 'POST',
		'permission_callback' => fn($req) => current_user_can('edit_post', (int) $req['id']),
		'callback' => 'bm_event_state',
	]);
	register_rest_route('bm/v1', '/event/(?P<id>\d+)/clear', [
		'methods' => 'POST',
		'permission_callback' => fn($req) => current_user_can('edit_post', (int) $req['id']),
		'callback' => function ($req) {
			$id = (int) $req['id'];
			if (get_post_type($id) !== 'sp_event') return new WP_Error('bm_not_event', 'To nie jest mecz', ['status' => 404]);
			foreach (['sp_player', 'sp_players', 'sp_results'] as $k) delete_post_meta($id, $k);
			return ['cleared' => $id];
		},
	]);

	global $wp_rest_additional_fields;
	if (isset($wp_rest_additional_fields['sp_event']['timeline'])) return; // wtyczka testowa (bm-test) już je wystawia
	register_rest_field('sp_event', 'timeline', [
		'get_callback'    => fn($o) => (object) (get_post_meta($o['id'], 'sp_timeline', true) ?: []),
		'update_callback' => fn($v, $post) => update_post_meta($post->ID, 'sp_timeline', $v),
		'schema'          => ['type' => 'object', 'context' => ['view', 'edit']],
	]);
});
