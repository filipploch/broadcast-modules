def get_current_time_in_seconds(period_id):
            # Czas zdarzenia — z in-memory cache timera (aktualny elapsed_ms),
        # z fallbackiem na DB (ostatni zsynchronizowany stan).
        # WAŻNE: cache jest indeksowany przez plugin_timer_id (np. "main-p2"),
        # nie przez DB id — stąd używamy main_timer.plugin_timer_id jako klucza.
        from core.managers import get_timer_manager
        tm = get_timer_manager()
        main_timer    = tm.get_active_main_timer(period_id)
        plugin_timer_id = main_timer.plugin_timer_id if main_timer else None
        timer_state   = tm.get_timer_state(plugin_timer_id) if plugin_timer_id else None

        if timer_state is not None:
            # Cache aktualny — używaj go (najbardziej aktualny elapsed_ms z ticków)
            elapsed_ms = timer_state.get('elapsed_time', 0)
        elif main_timer is not None:
            # Cache zimny (np. po restarcie serwera) — fallback na DB
            elapsed_ms = main_timer.elapsed_time_ms
        else:
            elapsed_ms = 0

        from core.managers.period_manager import PeriodManager
        period_manager = PeriodManager()
        period         = period_manager.get_period_by_id(period_id)
        # game_time zapisujemy w sekundach (spójnie z game_time_formatted i _build_goal_entry)
        # initial_time okresu to suma limitów poprzednich części w ms → dzielimy przez 1000
        initial_s = period.initial_time // 1000
        elapsed_s = elapsed_ms // 1000
        game_time = elapsed_s + initial_s
        return game_time