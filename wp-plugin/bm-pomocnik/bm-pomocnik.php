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

add_action('rest_api_init', function () {
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
