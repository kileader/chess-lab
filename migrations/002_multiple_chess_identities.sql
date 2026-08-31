ALTER TABLE account_player_identities DROP CONSTRAINT account_player_identities_pkey;
ALTER TABLE account_player_identities ADD PRIMARY KEY (user_id, platform, username_normalized);
