#!/bin/bash
YESTERDAY=$(python -c "from datetime import date, timedelta; print(date.today() - timedelta(days=1))")
TODAY=$(python -c "from datetime import date; print(date.today())")
echo "Syncing records from $YESTERDAY to $TODAY ..."
python etl/extract.py --from-date "$YESTERDAY" --to-date "$TODAY"
