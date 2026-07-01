CREATE TABLE IF NOT EXISTS ncaa_hitting_stats (
    player_name VARCHAR(100) NOT NULL,
    team VARCHAR(100) NOT NULL,
    games_played INT DEFAULT 0,
    at_bats INT DEFAULT 0,
    hits INT DEFAULT 0,
    home_runs INT DEFAULT 0,
    walks INT DEFAULT 0,
    strikeouts INT DEFAULT 0,
    last_updated TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (player_name, team)
);

-- (Garde la table ncaa_hitting_stats existante au dessus)

CREATE TABLE IF NOT EXISTS scout_grades (
    player_name VARCHAR(100) NOT NULL,
    scout_name VARCHAR(100) NOT NULL,
    hit_grade INT CHECK (hit_grade BETWEEN 20 AND 80),
    power_grade INT CHECK (power_grade BETWEEN 20 AND 80),
    run_grade INT CHECK (run_grade BETWEEN 20 AND 80),
    arm_grade INT CHECK (arm_grade BETWEEN 20 AND 80),
    field_grade INT CHECK (field_grade BETWEEN 20 AND 80),
    overall_fv INT CHECK (overall_fv BETWEEN 20 AND 80), -- Future Value
    report_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (player_name, scout_name)
);