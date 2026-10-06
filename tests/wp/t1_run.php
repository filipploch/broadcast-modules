<?php
// T1: laduje scenariusze z t1_scen.json do SportsPress i zwraca kolejnosc tabeli (SportsPress + Advanced H2H)
$scen = json_decode(file_get_contents(getenv('BM_OUT') . '/t1_scen.json'), true);
$only = getenv('T1_ONLY'); // opcjonalnie: ograniczenie liczby scenariuszy
if ($only) $scen = array_slice($scen, 0, (int)$only);

function t1_col($slug, $title, $eq) {
	if (get_page_by_path($slug, OBJECT, 'sp_column')) return;
	$id = wp_insert_post(['post_type'=>'sp_column','post_title'=>$title,'post_name'=>$slug,'post_status'=>'publish']);
	update_post_meta($id, 'sp_equation', $eq); update_post_meta($id, 'sp_precision', 0);
}
t1_col('wa', 'WA', '$win_away');
t1_col('gdg', 'GDG', '$goalsfor - $goalsagainst');

function t1_crit($slug, $title, $regular, $tiebreak) {
	$ex = get_page_by_path($slug, OBJECT, 'sah2h_criteria');
	$id = $ex ? $ex->ID : wp_insert_post(['post_type'=>'sah2h_criteria','post_title'=>$title,'post_name'=>$slug,'post_status'=>'publish']);
	update_post_meta($id, 'sah2h_column_order', $regular);
	update_post_meta($id, 'sah2h_tiebreak_order', $tiebreak);
}
$c = fn($col, $h2h=false) => ['column'=>$col, 'order'=>'DESC'] + ($h2h ? ['h2h_only'=>'1'] : []);
t1_crit('t1-nalf', 'T1 NALF', [$c('pts')], [$c('pts',true), $c('gd',true), $c('gdg'), $c('f')]);
t1_crit('t1-mzpn', 'T1 MZPN', [$c('pts')], [$c('pts',true), $c('gd',true), $c('gdg'), $c('f'), $c('w'), $c('wa')]);

$res = [];
foreach ($scen as $s) {
	$lg = wp_insert_term('T1L'.$s['id'].'-'.uniqid(), 'sp_league'); $ss = wp_insert_term('T1S'.$s['id'].'-'.uniqid(), 'sp_season');
	$lg = $lg['term_id']; $ss = $ss['term_id'];
	$tid = [];
	foreach ($s['teams'] as $t) {
		$tid[$t] = wp_insert_post(['post_type'=>'sp_team','post_title'=>'Z'.sprintf('%02d',$t),'post_status'=>'publish']);
		wp_set_object_terms($tid[$t], [$lg], 'sp_league'); wp_set_object_terms($tid[$t], [$ss], 'sp_season');
	}
	foreach ($s['games'] as $i => $g) {
		[$h,$a,$hg,$ag] = $g;
		$e = wp_insert_post(['post_type'=>'sp_event','post_title'=>"S{$s['id']} $h-$a",'post_status'=>'publish','post_date'=>date('Y-m-d H:i:s', strtotime('-60 days') + $i*3600)]);
		add_post_meta($e,'sp_team',$tid[$h]); add_post_meta($e,'sp_team',$tid[$a]);
		update_post_meta($e,'sp_format','league');
		$oh = $hg>$ag?'win':($hg==$ag?'draw':'loss'); $oa = $hg>$ag?'loss':($hg==$ag?'draw':'win');
		update_post_meta($e,'sp_results',[$tid[$h]=>['goals'=>(string)$hg,'outcome'=>[$oh]], $tid[$a]=>['goals'=>(string)$ag,'outcome'=>[$oa]]]);
		wp_set_object_terms($e,[$lg],'sp_league'); wp_set_object_terms($e,[$ss],'sp_season');
	}
	$inv = array_flip($tid);
	foreach (['NALF'=>'t1-nalf','MZPN'=>'t1-mzpn'] as $rule=>$slug) {
		$tb = wp_insert_post(['post_type'=>'sp_table','post_title'=>"T1 {$s['id']} $rule",'post_status'=>'publish']);
		update_post_meta($tb,'sp_select','manual'); foreach ($tid as $t) add_post_meta($tb,'sp_team',$t);
		wp_set_object_terms($tb,[$lg],'sp_league'); wp_set_object_terms($tb,[$ss],'sp_season');
		update_post_meta($tb,'sah2h_criteria',$slug);
		$t = new SAH2H_League_Table($tb); $t->h2h_criteria = $slug;
		$d = $t->data(); unset($d[0]);
		$res[$s['id']][$rule] = array_map(fn($id)=>$inv[$id], array_keys($d));
	}
}
file_put_contents(getenv('BM_OUT') . '/t1_out.json', json_encode($res));
echo count($res), " scenariuszy policzonych\n";
