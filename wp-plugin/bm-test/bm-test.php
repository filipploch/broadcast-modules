<?php
/** Wtyczka TESTOWA do testow wykonalnosci T2, T4, T5 (nie jest docelowym pluginem). */

// --- T5: pola wlasne w REST
add_action('init', function () {
	foreach (['sp_team','sp_event'] as $pt) add_post_type_support($pt, 'custom-fields');
	$s = fn($t='string') => ['show_in_rest'=>true, 'single'=>true, 'type'=>$t];
	foreach (['bm_name14','bm_abbr3','bm_source','bm_source_id'] as $k) register_post_meta('sp_team', $k, $s());
	register_post_meta('sp_team', 'bm_kits', ['show_in_rest'=>['schema'=>['type'=>'object','additionalProperties'=>true]], 'single'=>true, 'type'=>'object']);
	foreach (['bm_source','bm_source_id'] as $k) register_post_meta('sp_event', $k, $s());
	register_post_meta('sp_event', 'bm_live',   $s('boolean'));
	register_post_meta('sp_event', 'bm_locked', $s('boolean'));
});

// --- T4: minuty zdarzen (wolna wersja trzyma je w meta sp_timeline, ale REST jej nie wystawia)
add_action('rest_api_init', function () {
	register_rest_field('sp_event', 'timeline', [
		'get_callback'    => fn($o) => (object) (get_post_meta($o['id'], 'sp_timeline', true) ?: []),
		'update_callback' => fn($v, $post) => update_post_meta($post->ID, 'sp_timeline', $v),
		'schema'          => ['type'=>'object', 'context'=>['view','edit']],
	]);

	// --- T2: dwie tabele w jednej odpowiedzi
	register_rest_route('bm/v1', '/table/(?P<id>\d+)', [
		'methods' => 'GET', 'permission_callback' => '__return_true',
		'callback' => function ($req) {
			$id = (int) $req['id'];
			$crit = get_post_meta($id, 'sah2h_criteria', true);
			$calc = function () use ($id, $crit) {
				if ($crit && $crit !== 'default' && class_exists('SAH2H_League_Table')) { $t = new SAH2H_League_Table($id); $t->h2h_criteria = $crit; }
				else $t = new SP_League_Table($id);
				$d = $t->data(); unset($d[0]);
				$o = [];
				foreach ($d as $tid => $r) $o[] = ['team'=>(int)$tid,'name'=>get_the_title($tid),'pos'=>$r['pos'],'p'=>$r['p']??null,'pts'=>$r['pts']??null,'gd'=>$r['gd']??null,'f'=>$r['f']??null];
				return $o;
			};
			$virtual = $calc();                                       // wszystkie mecze z wynikiem, takze trwajacy
			$f = function ($args) {                                  // oficjalna: bez meczow z flaga "mecz trwa"
				$args['meta_query'][] = ['relation'=>'OR', ['key'=>'bm_live','compare'=>'NOT EXISTS'], ['key'=>'bm_live','value'=>'1','compare'=>'!=']];
				return $args;
			};
			add_filter('sportspress_table_data_event_args', $f);
			$official = $calc();
			remove_filter('sportspress_table_data_event_args', $f);
			return ['official'=>$official, 'virtual'=>$virtual];
		},
	]);
});
