ALTER TABLE account_player_identities DROP CONSTRAINT account_player_identities_platform_check;
ALTER TABLE account_player_identities ADD CONSTRAINT account_player_identities_platform_check
    CHECK(platform IN ('lichess', 'chess_com', 'other'));
