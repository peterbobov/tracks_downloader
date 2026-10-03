"""Tests for choosing the right track from the bot's search-results menu"""

from src.telegram_client import pick_search_result, is_search_results

# Real button layout from LosslessRobot (track rows, then paging, then "download page")
BENNY_BUTTONS = [
    'Benny Benassi - Satisfaction [4:45]',
    'Benny Benassi - Satisfaction (RL Grime Remix) [4:19]',
    'Benny Benassi - Satisfaction (Hyper Remix) [2:42]',
    'Alon Renser - Satisfaction (Benny Benassi Cover) [3:52]',
    'Ameritz Countdown Karaoke - Satisfaction (In the Style of Benny Benassi) [Karaoke Version] [2:23]',
    'VALHALLA IX - Satisfaction (Benny Benassi cover) [3:53]',
    '◉', '1 / 16', '→',
    '💾 Скачать страницу',
]

CRYSTAL_BUTTONS = [
    "Crystal Waters - Gypsy Woman (She's Homeless) (La Da Dee La Da Da) (Radio Edit) [3:37]",
    "Crystal Waters - Gypsy Woman (She's Homeless) (La Da Dee La Da Da) (Basement Boy Strip To The Bone Mix) [7:29]",
    "Crystal Waters - Gypsy Woman (She's Homeless) (La Da Dee La Da Da) (98 Remix) [8:31]",
    "Crystal Waters, RobbieG - Gypsy Woman (She's Homeless) (La Da Dee La Da Da) - RobbieG Remix [3:12]",
    '◉', '1 / 9', '→',
    '💾 Скачать страницу',
]

FLO_RIDA_BUTTONS = [
    'Future Hitmakers - Low (A Tribute to Flo Rida & T-Pain) [4:03]',
    'Flo Rida - Low (feat. T-Pain) [3:51]',
    'Studio Allstars - Low - (Tribute to Flo Rida Ft. T-Pain) [4:03]',
    'Flo Rida - Low [3:50]',
    'Urban Beats - Low (Made Famous by Flo Rida & T-Pain) [4:03]',
    'Urban DJs - Low (Made Famous by Flo Rida & T-Pain) [4:03]',
]

PREMIUM_PROMO_BUTTONS = ['😎 Подключить Premium со скидкой']
QUALITY_MENU_BUTTONS = ['📼 Low', 'High (16bit) 💿', '📀 Max (До 24bit/192kHz) ✅', '← Назад']


def ms(minutes, seconds):
    return (minutes * 60 + seconds) * 1000


def test_detects_search_results():
    assert is_search_results(BENNY_BUTTONS)
    assert is_search_results(FLO_RIDA_BUTTONS)
    assert not is_search_results(PREMIUM_PROMO_BUTTONS)
    assert not is_search_results(QUALITY_MENU_BUTTONS)


def test_picks_extended_by_duration_even_without_version_label():
    # Spotify: "Satisfaction - Isak Original Extended" 4:45; bot labels it just "Satisfaction"
    idx = pick_search_result(BENNY_BUTTONS, 'Benny Benassi, The Biz',
                             'Satisfaction - Isak Original Extended', ms(4, 45))
    assert idx == 0


def test_picks_named_mix_within_tolerance():
    idx = pick_search_result(CRYSTAL_BUTTONS, 'Crystal Waters, The Basement Boys',
                             "Gypsy Woman (She's Homeless) (La Da Dee La Da Da) - Basement Boy Strip To The Bone Mix",
                             ms(7, 31))
    assert idx == 1


def test_prefers_closest_duration_and_skips_tributes():
    idx = pick_search_result(FLO_RIDA_BUTTONS, 'Flo Rida, T-Pain', 'Low (feat. T-Pain)', ms(3, 51))
    assert idx == 1


def test_no_match_when_no_version_has_right_length():
    idx = pick_search_result(BENNY_BUTTONS, 'Benny Benassi, The Biz', 'Satisfaction - Club Mix', ms(6, 10))
    assert idx is None


def test_never_picks_non_track_buttons():
    assert pick_search_result(PREMIUM_PROMO_BUTTONS, 'Anyone', 'Anything', ms(3, 0)) is None
    assert pick_search_result(QUALITY_MENU_BUTTONS, 'Anyone', 'Low', ms(3, 0)) is None


def test_without_duration_falls_back_to_strict_title_match():
    # Resumed sessions may lack duration; then version markers must agree
    assert pick_search_result(BENNY_BUTTONS, 'Benny Benassi', 'Satisfaction (RL Grime Remix)', 0) == 1
    assert pick_search_result(BENNY_BUTTONS, 'Benny Benassi', 'Satisfaction - Extended', 0) is None


# MARK: - Matching the file the bot sends after a selection

from src.telegram_client import file_matches_selection


def test_file_matches_selected_result():
    # Real metadata of the file LosslessRobot sent after clicking 'Benny Benassi - Satisfaction [4:45]'
    metadata = {'title': 'Satisfaction', 'performer': 'Benny Benassi, The Biz', 'duration': 285}
    assert file_matches_selection('Benny Benassi - Satisfaction [4:45]', metadata)


def test_file_from_other_selection_does_not_match():
    remix = {'title': 'Satisfaction (RL Grime Remix)', 'performer': 'Benny Benassi, The Biz', 'duration': 259}
    assert not file_matches_selection('Benny Benassi - Satisfaction [4:45]', remix)


def test_file_with_wrong_length_does_not_match():
    metadata = {'title': 'Satisfaction', 'performer': 'Benny Benassi', 'duration': 200}
    assert not file_matches_selection('Benny Benassi - Satisfaction [4:45]', metadata)


def test_no_selection_or_metadata_never_matches():
    assert not file_matches_selection(None, {'title': 'x', 'performer': 'y', 'duration': 1})
    assert not file_matches_selection('Benny Benassi - Satisfaction [4:45]', {})


# MARK: - Length check for files matched by name

from src.telegram_client import duration_agrees


def test_duration_agrees_within_tolerance():
    assert duration_agrees({'duration': 449}, ms(7, 31))   # Crystal Waters: 7:29 vs Spotify 7:31


def test_duration_rejects_other_version():
    # The RL Grime Remix (4:19) must never be saved as the 4:45 Isak Original Extended
    assert not duration_agrees({'duration': 259}, ms(4, 45))


def test_duration_unknown_on_either_side_is_not_a_veto():
    assert duration_agrees({}, ms(4, 45))
    assert duration_agrees({'duration': 259}, 0)


# MARK: - False negatives found in real runs

def test_special_latin_letters_in_artist():
    buttons = ['Kasper Bjorke - Heaven (Nicolas Jaar Remix) [5:17]']
    assert pick_search_result(buttons, 'Kasper Bjørke, Nicolas Jaar', 'Heaven - Nicolas Jaar Remix', 317_100) == 0


def test_spotify_artist_credited_in_bot_title():
    # Spotify credits the remixer; the bot credits the original artist
    buttons = ['Theo Parrish - Falling Up (Carl Craig 2013 Remaster) [8:25]']
    assert pick_search_result(buttons, 'Carl Craig', 'Falling Up - Carl Craig 2013 Remaster', 505_900) == 0


def test_mix_name_variation_with_matching_length():
    buttons = [
        "Wamdue Project - King of My Castle - Roy Malone's King Radio Edit [3:35]",
        'Wamdue Project - King of My Castle - Roy Malone Kings Main Mix [4:58]',
        'Wamdue Project - King of My Castle [3:26]',
    ]
    assert pick_search_result(buttons, 'Wamdue Project, Roy Malone',
                              "King of My Castle (Roy Malone's King Mix)", ms(4, 59) + 700) == 1


def test_exact_title_allows_up_to_15s_length_difference():
    buttons = ['Key Tronics Ensemble - Calypso of House - Paradise Mix [9:21]',
               'Key Tronics Ensemble - House Of Calypso [8:33]']
    assert pick_search_result(buttons, 'Key Tronics Ensemble', 'Calypso of House - Paradise Mix', ms(9, 8)) == 0

    buttons = ['Kings of Tomorrow - Finally - Kevin Yost Dubified Remix [6:28]',
               'Kings of Tomorrow - Finally [5:11]']
    assert pick_search_result(buttons, 'Kings Of Tomorrow, Julie Mc Knight', 'Finally', ms(5, 15) + 800) == 1


def test_15s_rule_never_accepts_other_versions():
    # Different version marker (remix/dub) or partial title: still rejected even if close in length
    assert pick_search_result(['Tour-Maubourg - Ode to Love (Saudade Remix) [4:36]'],
                              'Tour-Maubourg', 'Ode to Love', ms(4, 21)) is None
    assert pick_search_result(['Cobblestone Jazz - Chance [7:58]'],
                              'Cobblestone Jazz', 'Chance Dub', ms(7, 41)) is None
    assert pick_search_result(['The Believers - Believe [8:20]'],
                              'The Believers', 'Who Dares to Believe in Me?', ms(8, 11)) is None
    # Exact title but more than 15s apart
    assert pick_search_result(['Traumer - Classroom [6:08]'], 'Traumer', 'Classroom', ms(8, 36)) is None


def test_direct_file_length_rule_matches_menu_rule():
    # A file 4.8s shorter with the exact title is accepted; a remix 26s shorter is not
    assert duration_agrees({'duration': 311, 'title': 'Finally'}, ms(5, 15) + 800, 'Finally')
    assert not duration_agrees({'duration': 259, 'title': 'Satisfaction (RL Grime Remix)'},
                               ms(4, 45), 'Satisfaction - Isak Original Extended')
    assert not duration_agrees({'duration': 311, 'title': 'Something Else'}, ms(5, 15) + 800, 'Finally')


def test_artist_named_only_in_title_requires_same_version():
    # "Benny Benassi" appears in these titles, but they are a cover and a karaoke version
    buttons = ['Alon Renser - Satisfaction (Benny Benassi Cover) [4:45]',
               'Ameritz Countdown Karaoke - Satisfaction (In the Style of Benny Benassi) [Karaoke Version] [4:45]']
    assert pick_search_result(buttons, 'Benny Benassi', 'Satisfaction', ms(4, 45)) is None
