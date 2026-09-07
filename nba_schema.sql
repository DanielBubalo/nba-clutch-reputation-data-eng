CREATE TABLE players (
    player_id INT PRIMARY KEY,
    player_name VARCHAR(50) NOT NULL
);

CREATE TABLE teams (
    team_id INT PRIMARY KEY,
    team_abv CHAR(3),
    team_name VARCHAR(50) NOT NULL
);

CREATE TABLE player_advanced_stats (
    player_id INT,
    season VARCHAR(7),
    team_id INT,
    team_abv CHAR(3),
    age INT,
    games_played INT,
    minutes DECIMAL,
    offensive_rating DECIMAL,
    defensive_rating DECIMAL,
    net_rating DECIMAL,
    effective_field_goal_pct DECIMAL,
    true_shooting_pct DECIMAL,
    usage_pct DECIMAL,
    player_impact_estimate DECIMAL,
    possessions INT,
    assist_pct DECIMAL,
    rebound_pct DECIMAL,
    PRIMARY KEY (player_id, season),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (team_id) REFERENCES teams(team_id)
);

CREATE TABLE clutch_advanced_stats (
    player_id INT,
    season VARCHAR(7),
    games_played INT,
    minutes DECIMAL,
    effective_field_goal_pct DECIMAL,
    true_shooting_pct DECIMAL,
    usage_pct DECIMAL,
    net_rating DECIMAL,
    player_impact_estimate DECIMAL,
    field_goals_attempted INT,
    assist_pct DECIMAL,
    rebound_pct DECIMAL,
    PRIMARY KEY (player_id, season),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE TABLE home_clutch_stats (
    player_id INT,
    season VARCHAR(7),
    games_played INT,
    true_shooting_pct DECIMAL,
    net_rating DECIMAL,
    usage_pct DECIMAL,
    PRIMARY KEY (player_id, season),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE TABLE road_clutch_stats (
    player_id INT,
    season VARCHAR(7),
    games_played INT,
    true_shooting_pct DECIMAL,
    net_rating DECIMAL,
    usage_pct DECIMAL,
    PRIMARY KEY (player_id, season),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
);

CREATE TABLE primary_defenders_stats (
    player_id INT,
    player_name VARCHAR(50),
    season VARCHAR(7),
    defensive_player_id INT,
    defensive_player_name VARCHAR(50),
    matchup_minutes VARCHAR(10),
    PRIMARY KEY (player_id, season, defensive_player_id),
    FOREIGN KEY (player_id) REFERENCES players(player_id),
    FOREIGN KEY (defensive_player_id) REFERENCES players(player_id)
);

CREATE TABLE player_awards (
    player_id INT,
    season VARCHAR(7),
    award VARCHAR(50),
    PRIMARY KEY (player_id, season, award),
    FOREIGN KEY (player_id) REFERENCES players(player_id)
)