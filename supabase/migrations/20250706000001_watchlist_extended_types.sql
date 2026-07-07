-- Extend watchlist item types for saved signals, bets, and parlays
ALTER TABLE watchlist_items DROP CONSTRAINT IF EXISTS watchlist_items_item_type_check;

ALTER TABLE watchlist_items ADD CONSTRAINT watchlist_items_item_type_check
  CHECK (item_type IN (
    'ticker',
    'sport_event',
    'team',
    'sport_bet',
    'parlay',
    'stock_signal',
    'option_signal'
  ));
