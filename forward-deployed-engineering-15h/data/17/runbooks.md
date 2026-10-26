# Runbook: 1. Triage is slow

## Symptom
alert: more than 1 in 4 triage requests take over 1 s

## First check
a slow log line and its trace_id; in the trace, the slowest span is the GET to the customer API

## Mitigate
do not restart triage, it will not help, because the time is spent in the customer's API span; send the customer's API owner the trace_id and the times

## Verify
one /triage call returns in under 1 s, and the alert clears within 5 minutes

## Escalate to
the customer's API team (their on-call), with the time window

# Runbook: 2. The customer API rejects triage's token

## Symptom
triage answers 502; logs show erp_error with erp_status 401 or 403

## First check
did the customer rotate the reader secret? Ask them; never paste a secret into chat or a ticket

## Mitigate
the customer puts the current secret in its secret store; redeploy the same image tag with it (lessons 13, 14)

## Verify
one /triage call returns 200, and no new erp_error lines appear

## Escalate to
the customer's identity team, if the reader account is locked

# Runbook: 3. A bad release writes wrong labels

## Symptom
the customer reports labels changed since the last release; a sample of 10 orders disagrees with the eval set

## First check
which tag is running (the version field) and when it was deployed

## Mitigate
roll back to the last good tag (TRIAGE_TAG=<tag>; the images are kept), then restore the decisions store from the backup taken before the release; decisions written after the backup are lost, so tell the customer the time window

## Verify
the sample of 10 agrees with the eval set; the restore drill checks only prove the backup is sound, so this sample is the real check on the live store

## Escalate to
the customer's operations lead, with the list of affected orders
