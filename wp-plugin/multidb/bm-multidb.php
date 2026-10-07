<?php
/**
 * Wybor bazy rozgrywek (SQLite) i adresu strony wedlug portu zadania: jeden kod WordPressa, wiele baz.
 *
 * Dolaczany z wp-config.php PRZED ustawieniem pozostalych stalych:
 *     define( 'BM_DB_BASE', '<katalog z bazami>' );
 *     require '<repo>/wp-plugin/multidb/bm-multidb.php';
 *
 * Port 8090 = baza domyslna (wp-content/database/.ht.sqlite), kazdy inny port = BM_DB_BASE/p<port>/.ht.sqlite.
 * Zmienna srodowiskowa BM_DB=<nazwa> wybiera baze BM_DB_BASE/<nazwa>/ wprost (szablon, WP-CLI), BM_PORT wybiera port dla WP-CLI.
 */
$bm_port = (string) ( $_SERVER['SERVER_PORT'] ?? getenv( 'BM_PORT' ) ?: '8090' );
$bm_name = getenv( 'BM_DB' ) ?: ( '8090' === $bm_port ? '' : 'p' . $bm_port );

if ( '' !== $bm_name ) {
	define( 'DB_DIR', BM_DB_BASE . '/' . $bm_name . '/' );
	define( 'DB_FILE', '.ht.sqlite' );
	define( 'UPLOADS', 'wp-content/uploads/' . $bm_name );   // osobne pliki (loga) dla kazdej bazy
}
// adres wynika z portu, wiec skopiowana baza dziala bez zmiany opcji; rozne adresy = rozne ciasteczka panelu
define( 'WP_HOME', 'http://127.0.0.1:' . $bm_port );
define( 'WP_SITEURL', WP_HOME );
