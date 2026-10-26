# Security evidence pack (lab, invented data)

## Q1 [residency] answered (lab)
Where is customer data stored? Name the region.
- Evidence: setting STORAGE_REGION, against ALLOWED_REGIONS (rerun on production)

## Q2 [residency] answered (lab)
Which region does the model provider process prompts in?
- Evidence: setting MODEL_REGION, against ALLOWED_REGIONS (rerun on production)

## Q3 [PII] answered (lab)
How is personal data removed before records are stored?
- Evidence: scan of data/27/records_stored.csv (rerun on production)

## Q4 [audit] answered (lab)
Is every write to customer data logged with who did it and when?
- Evidence: audit.jsonl: one line per write (rerun on production)

## Q5 [audit] answered (lab)
Can an audit log entry hold a secret or personal data?
- Evidence: audit.jsonl: every line scanned (rerun on production)

## Q6 [access] answered (lab)
How long do access tokens live, and how are they scoped?
- Evidence: apps/13/customer_api.py (lesson 13) (rerun on production)

## Q7 [retention] answered (lab)
How long are triage records kept, and when are they deleted?
- Evidence: setting RETENTION_DAYS, against the contract maximum (rerun on production)

## Q8 [assurance] GAP
Do you hold a SOC 2 Type II report for this service?
- Evidence: none in the lab: no SOC 2 report exists, so none is claimed
