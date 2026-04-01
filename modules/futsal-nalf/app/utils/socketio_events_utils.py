def _round_nr_to_round_name(_round_nr, _league_name):
    if not _round_nr or _round_nr == 0:
        return ''
    if not _league_name:
        return str(_round_nr)
    if 'Dywizja' in _league_name:
        _division = _league_name.replace('Dywizja', 'Dywizji')
        return f'{_round_nr}. kolejka {_division}'
    if 'Puchar' in _league_name:
        _cup = _league_name.replace('Puchar', 'Pucharu')
        cup_rounds = {
            '1': '1/16 finału',
            '2': '1/8 finału',
            '3': 'Ćwierćfinał',
            '4': 'Półfinał',
            '5': 'Mecz o 3. miejsce',
            '6': 'Finał'
        }
        print(f'round name: {cup_rounds[str(_round_nr)]} {_cup}')
        return f'{cup_rounds[str(_round_nr)]} {_cup}'
    return ''

def _get_dict(_structure):
    from dataclasses import asdict
    return asdict(_structure)

def generate_show_overlay_data(data):
    from app.models.settings import Settings
    settings = Settings.get_settings()
    from app.models.game import Game
    current_game_data = Game.query.get(settings.current_game_id).to_dict()
    container_id = data.get('container_id')
    match container_id:
        case 'game-container':
            pass
        case 'home-team-squad-container':
            data.update({
                'team_name': current_game_data['home_team_name'],
                'team_short_name': current_game_data['home_team_short_name'],
                'team_squad': current_game_data['home_team_squad'],
                'logo': current_game_data['home_team_logo']
                })
        case 'away-team-squad-container':
            data.update({
                'team_name': current_game_data['away_team_name'],
                'team_short_name': current_game_data['away_team_short_name'],
                'team_squad': current_game_data['away_team_squad'],
                'logo': current_game_data['away_team_logo']
                })
        case 'start-container':
            data.update({
                'league_group_nr': current_game_data['group_nr'],
                'round': current_game_data['round'],
                'referees': current_game_data['referees'],
                'commentators': current_game_data['commentators'],
                'date': current_game_data['date'],
                'stadium': current_game_data['stadium'],
                'round_name': _round_nr_to_round_name(current_game_data['round'], current_game_data['league_name']),
                'home_team_name': current_game_data['home_team_name'],
                'home_team_short_name': current_game_data['home_team_short_name'],
                'home_team_logo': current_game_data['home_team_logo'],
                'away_team_name': current_game_data['away_team_name'],
                'away_team_short_name': current_game_data['away_team_short_name'],
                'away_team_logo': current_game_data['away_team_logo']
            })
        case 'break-container':
            from app.managers.game_event_manager import GameEventManager
            manager = GameEventManager()
            scorers = _get_dict(manager.get_goals_summary(game_id=settings.current_game_id))
            data.update({
                'round_name': _round_nr_to_round_name(current_game_data['round'], current_game_data['league_name']),
                'result': current_game_data['score_string'],
                'home_team_logo': current_game_data['home_team_logo'],
                'away_team_logo': current_game_data['away_team_logo'],
                'home_team_scorers': scorers['home'],
                'away_team_scorers': scorers['away']
            })
        case 'empty-container':
            pass
    return data
