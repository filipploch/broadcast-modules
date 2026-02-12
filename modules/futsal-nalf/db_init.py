"""Database initialization script with seed data"""
from app import create_app
from app.extensions import db
from app.models import (
    # Plugin,
    Settings,
    Season,
    League,
    Team,
    LeagueTeam,
    Stadium,
    Game
)
from datetime import datetime

def init_database():
    """Initialize database with tables and seed data"""
    print("=" * 80)
    print(" " * 20 + "DATABASE INITIALIZATION")
    print("=" * 80)

    app = create_app('development')

    with app.app_context():
        print("\n📋 Step 1: Creating database tables...")
        db.create_all()
        print("   ✅ Tables created successfully")

        # Verify tables
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"\n📊 Step 2: Verifying tables ({len(tables)} found)")
        for table in sorted(tables):
            print(f"   - {table}")

        # Check if database already has data
        existing_count = Season.query.count()
        if existing_count > 0:
            print(f"\n⚠️  Database already contains data ({existing_count} seasons)")
            print("   Skipping seed data insertion")
            return

        print("\n🌱 Step 3: Seeding initial data...\n")

        try:
            # ========== PLUGINS ==========
            # print("   📦 Adding Plugins...")
            #
            # timer_plugin = Plugin(
            #     id='timer-plugin',
            #     name='Timer Plugin',
            #     type='timer',
            #     executable_path='../../plugins/timer-plugin/timer-plugin.exe',
            #     expected_host='localhost',
            #     expected_port=0,
            #     is_critical=True,
            #     startup_priority=10,
            #     startup_delay_ms=500
            # )
            # timer_plugin.config = {
            #     'plugin_id': 'timer-plugin',
            #     'hub_url': 'ws://localhost:8080/ws',
            #     'auto_reconnect': True,
            #     'max_reconnects': 5,
            #     'update_interval_ms': 100
            # }
            # db.session.add(timer_plugin)
            # print("      ✅ Timer Plugin")

            # ========== SEASON ==========
            print("\n   🏆 Adding Season...")
            season = Season(
                id=1,
                number=30,
                name="Jesień 2025"
            )
            db.session.add(season)
            print(f"      ✅ {season.name}")

            # ========== LEAGUES ==========
            print("\n   🏅 Adding Leagues...")

            league_a = League(
                id=1,
                season_id=1,
                name="Dywizja A",
                games_url="https://nalffutsal.pl/?page_id=34",
                table_url="https://nalffutsal.pl/?page_id=16",
                scorers_url="https://nalffutsal.pl/?page_id=50",
                assists_url="https://nalffutsal.pl/?page_id=3191",
                canadian_url="https://nalffutsal.pl/?page_id=42"
            )
            db.session.add(league_a)
            print(f"      ✅ {league_a.name}")

            league_b = League(
                id=2,
                season_id=1,
                name="Dywizja B",
                games_url="https://nalffutsal.pl/?page_id=52",
                table_url="https://nalffutsal.pl/?page_id=36",
                scorers_url="https://nalffutsal.pl/?page_id=18",
                assists_url="https://nalffutsal.pl/?page_id=3274",
                canadian_url="https://nalffutsal.pl/?page_id=44"
            )
            db.session.add(league_b)
            print(f"      ✅ {league_b.name}")

            league_cup = League(
                id=3,
                season_id=1,
                name="Puchar Ligi",
                games_url="https://nalffutsal.pl/?page_id=32",
                table_url=None,
                scorers_url="https://nalffutsal.pl/?page_id=38",
                assists_url="https://nalffutsal.pl/?page_id=3317",
                canadian_url="https://nalffutsal.pl/?page_id=54"
            )
            db.session.add(league_cup)
            print(f"      ✅ {league_cup.name}")

            # ========== TEAMS ==========
            print("\n   ⚽ Adding Teams...")

            team_iglomen = Team(
                id=1,
                name="IGLOMEN",
                name_20="Iglomen",
                short_name="IGL",
                team_url="https://nalffutsal.pl/?sp_team=bidvest-krakow"
            )
            db.session.add(team_iglomen)
            print(f"      ✅ {team_iglomen.name} ({team_iglomen.short_name})")

            team_galactik = Team(
                id=2,
                name="Galactik Futsal",
                name_20="Galactik Futsal",
                short_name="GAL",
                team_url="https://nalffutsal.pl/?sp_team=galactik-futsal"
            )
            db.session.add(team_galactik)
            print(f"      ✅ {team_galactik.name} ({team_galactik.short_name})")

            # Add third team for examples
            team_example = Team(
                id=3,
                name="Example Team",
                name_20="Example Team",
                short_name="EXT",
                team_url="https://nalffutsal.pl/?sp_team=example-team"
            )
            db.session.add(team_example)
            print(f"      ✅ {team_example.name} ({team_example.short_name})")

            # ========== LEAGUE_TEAMS ==========
            print("\n   🔗 Adding League-Team Associations...")

            # Dywizja A: IGLOMEN, Example Team
            lt1 = LeagueTeam(id=1, league_id=1, team_id=1, group_nr=1)
            lt2 = LeagueTeam(id=2, league_id=1, team_id=3, group_nr=1)
            db.session.add_all([lt1, lt2])
            print(f"      ✅ Dywizja A: 2 teams")

            # Dywizja B: Galactik, Example Team
            lt3 = LeagueTeam(id=3, league_id=2, team_id=2, group_nr=1)
            lt4 = LeagueTeam(id=4, league_id=2, team_id=3, group_nr=1)
            db.session.add_all([lt3, lt4])
            print(f"      ✅ Dywizja B: 2 teams")

            # ========== STADIUM ==========
            print("\n   🏟️  Adding Stadium...")

            stadium = Stadium(
                id=1,
                name="Estadio Handlowe",
                address="Os. Handlowe 4",
                city="Kraków"
            )
            db.session.add(stadium)
            print(f"      ✅ {stadium.name}, {stadium.city}")

            # ========== GAMES ==========
            print("\n   📅 Adding Games...")

            game = Game(
                id=1,
                home_team_id=1,
                away_team_id=2,
                home_team_goals=None,
                away_team_goals=None,
                home_team_fouls=0,
                away_team_fouls=0,
                status=Game.STATUS_NOT_STARTED,
                league_id=3,
                group_nr=1,
                stadium_id=1,
                date=datetime(2026, 2, 28, 21, 30),
                round=1
            )
            db.session.add(game)
            print(f"      ✅ {team_iglomen.short_name} vs {team_galactik.short_name} (Round 1)")

            # ========== SETTINGS ==========
            print("\n   ⚙️  Adding Settings...")

            settings = Settings(
                id=1,
                current_season_id=1,
                current_game_id=1
            )
            db.session.add(settings)
            print(f"      ✅ Default settings (Season: {season.name}, Game: {game.id})")

            # ========== COMMIT ALL ==========
            print("\n💾 Step 4: Committing to database...")
            db.session.commit()
            print("   ✅ All data committed successfully!")

            # ========== VERIFICATION ==========
            print("\n📊 Step 5: Verification")
            # print(f"   - Plugins:      {Plugin.query.count()}")
            print(f"   - Settings:     {Settings.query.count()}")
            print(f"   - Seasons:      {Season.query.count()}")
            print(f"   - Leagues:      {League.query.count()}")
            print(f"   - Teams:        {Team.query.count()}")
            print(f"   - League-Teams: {LeagueTeam.query.count()}")
            print(f"   - Stadiums:     {Stadium.query.count()}")
            print(f"   - Games:        {Game.query.count()}")

            print("\n✅ DATABASE INITIALIZATION COMPLETE!")

        except Exception as e:
            db.session.rollback()
            print(f"\n❌ ERROR during initialization: {e}")
            import traceback
            traceback.print_exc()
            raise

    print("\n" + "=" * 80)

def reset_database():
    """Reset database - drop all tables and recreate"""
    print("=" * 80)
    print(" " * 20 + "⚠️  DATABASE RESET WARNING")
    print("=" * 80)
    print("\n❗ This will DELETE ALL DATA in the database!")
    print("   Are you sure you want to continue? (yes/no)")

    confirm = input("\n   > ").strip().lower()

    if confirm != 'yes':
        print("\n   ✅ Reset cancelled")
        print("\n" + "=" * 80)
        return

    app = create_app('development')

    with app.app_context():
        print("\n🗑️  Dropping all tables...")
        db.drop_all()
        print("   ✅ All tables dropped")

        print("\n🔨 Creating fresh tables...")
        db.create_all()
        print("   ✅ Tables created")

        print("\n✅ Database reset complete!")
        print("   Run 'python db_init.py init' to add seed data")

    print("\n" + "=" * 80)

def show_database_info():
    """Show database information"""
    print("=" * 80)
    print(" " * 20 + "DATABASE INFORMATION")
    print("=" * 80)

    app = create_app('development')

    with app.app_context():
        # Database path
        db_uri = app.config['SQLALCHEMY_DATABASE_URI']
        print(f"\n📍 Database: {db_uri}")

        # Tables
        inspector = db.inspect(db.engine)
        tables = inspector.get_table_names()
        print(f"\n📊 Tables ({len(tables)}):")

        for table in sorted(tables):
            columns = inspector.get_columns(table)
            print(f"\n   {table}:")
            for col in columns:
                nullable = "NULL" if col['nullable'] else "NOT NULL"
                print(f"      - {col['name']:30} {str(col['type']):20} {nullable}")

        # Record counts
        print(f"\n📈 Record counts:")
        # print(f"   - Plugins:      {Plugin.query.count():3}")
        print(f"   - Settings:     {Settings.query.count():3}")
        print(f"   - Seasons:      {Season.query.count():3}")
        print(f"   - Leagues:      {League.query.count():3}")
        print(f"   - Teams:        {Team.query.count():3}")
        print(f"   - League-Teams: {LeagueTeam.query.count():3}")
        print(f"   - Stadiums:     {Stadium.query.count():3}")
        print(f"   - Games:        {Game.query.count():3}")

        # Current settings
        settings = Settings.query.first()
        if settings:
            print(f"\n⚙️  Current Settings:")
            print(f"   - Active Season: {settings.current_season.name if settings.current_season else 'None'}")
            if settings.current_game:
                game = settings.current_game
                print(f"   - Active Game:   {game.home_team.short_name} vs {game.away_team.short_name} (ID: {game.id})")

    print("\n" + "=" * 80)

if __name__ == '__main__':
    import sys

    if len(sys.argv) > 1:
        command = sys.argv[1].lower()

        if command == 'init':
            init_database()
        elif command == 'reset':
            reset_database()
        elif command == 'info':
            show_database_info()
        else:
            print(f"❌ Unknown command: {command}")
            print("\n📚 Available commands:")
            print("   - init   : Initialize database with seed data")
            print("   - reset  : Drop all tables and recreate (WARNING: deletes data!)")
            print("   - info   : Show database information")
    else:
        # Default: initialize
        init_database()