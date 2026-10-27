<?php
/**
 * Plugin Name: BM Pomocnik (importery)
 * Description: Pola własne w REST dla importerów danych ze stron do SportsPressa (zalążek pluginu z etapu E3). Wgrywany jako mu-plugin.
 *
 * Pola (wszystkie tekstowe, widoczne w REST w polu "meta"):
 *  - bm_source, bm_source_id: źródło i identyfikator rekordu w źródle (drużyna, zawodnik, mecz); po nich importer dopasowuje rekordy,
 *  - bm_source_hash: skrót treści ze źródła; importer pomija zapis, gdy skrót się nie zmienił,
 *  - bm_logo (drużyna): ścieżka logo względem folderu logo modułu, np. "garbarnia/Garbarnia.png"; bm_name14 (drużyna): nazwa do 14 znaków dla nakładek, bm_short_name (drużyna): skrót do 3 znaków dla nakładek (edytowalny w panelu WP),
 *  - bm_first_name, bm_last_name (zawodnik): imię i nazwisko osobno (tytuł w WP to jedno pole); edytowalne w panelu WP (Pola własne).
 * Trasa bm/v1/event/<id>/clear (POST, wymaga prawa edycji): czyści wynik, skład i statystyki zawodników meczu (zapis przez REST SportsPressa
 * tylko scala dane, więc importer czyści mecz przed aktualizacją).
 * Mecz dodatkowo: bm_live, bm_locked (flagi, jak w pluginie testowym), a REST wystawia minuty zdarzeń (sp_timeline) w polu "timeline".
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
	foreach (['bm_live', 'bm_locked'] as $k) {
		register_post_meta('sp_event', $k, ['show_in_rest' => true, 'single' => true, 'type' => 'boolean']);
	}
});

add_action('rest_api_init', function () {
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
