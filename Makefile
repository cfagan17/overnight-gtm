EA_TEST_DSN ?= postgresql://postgres@localhost:5432/postgres
export EA_TEST_DSN

.PHONY: test report demo tools-json

test:
	python -m pytest tests -q

report:
	python scripts/attack_report.py --dsn "$(EA_TEST_DSN)"

demo:
	python scripts/build_db.py --dsn "$(EA_TEST_DSN)" --name ea_dev --seed

tools-json:
	python agents/runtime/tools.py > agents/runtime/tools.json
