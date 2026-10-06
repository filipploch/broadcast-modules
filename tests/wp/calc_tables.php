<?php
// Liczy tabele SportsPress + Advanced H2H dla podanych lig/sezonu. Wejscie: BM_OUT/calc_in.json
// [{"key":..., "league":id, "season":id, "teams":[id,...], "criteria":"t1-nalf"}], wyjscie: BM_OUT/calc_out.json
$in = json_decode(file_get_contents(getenv('BM_OUT') . '/calc_in.json'), true);
$out = [];
foreach ($in as $c) {
	$tb = wp_insert_post(['post_type'=>'sp_table','post_title'=>'calc '.$c['key'],'post_status'=>'publish']);
	update_post_meta($tb, 'sp_select', 'manual'); foreach ($c['teams'] as $t) add_post_meta($tb, 'sp_team', $t);
	wp_set_object_terms($tb, [$c['league']], 'sp_league'); wp_set_object_terms($tb, [$c['season']], 'sp_season');
	update_post_meta($tb, 'sah2h_criteria', $c['criteria']);
	$t = new SAH2H_League_Table($tb); $t->h2h_criteria = $c['criteria']; $d = $t->data(); unset($d[0]);
	$rows = [];
	foreach ($d as $id => $r) $rows[] = ['team'=>(int)$id, 'pos'=>$r['pos'], 'p'=>$r['p']??null, 'w'=>$r['w']??null, 'd'=>$r['d']??null, 'l'=>$r['l']??null, 'f'=>$r['f']??null, 'a'=>$r['a']??null, 'gd'=>$r['gd']??null, 'pts'=>$r['pts']??null];
	$out[$c['key']] = $rows;
}
file_put_contents(getenv('BM_OUT') . '/calc_out.json', json_encode($out));
echo "ok\n";
