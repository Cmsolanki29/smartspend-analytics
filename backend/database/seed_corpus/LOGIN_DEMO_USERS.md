# Fixed demo logins (pre-seeded DB)

Run once after DB is up (from `backend/`):

```bash
python -m scripts.seed_judge_demo_users
```

## Credentials (same password for all)

| # | Email | Password |
|---|-------|----------|
| 1 | judgedemo1@judge.smartspend.example.com | Pass@123 |
| 2 | judgedemo2@judge.smartspend.example.com | Pass@123 |
| 3 | judgedemo3@judge.smartspend.example.com | Pass@123 |
| 4 | judgedemo4@judge.smartspend.example.com | Pass@123 |
| 5 | judgedemo5@judge.smartspend.example.com | Pass@123 |
| 6 | judgedemo6@judge.smartspend.example.com | Pass@123 |

Use **Sign in** on the app (not sign up). Dashboard month picker should match **current calendar month** for MTD numbers.

Re-run the script anytime to reset these six users to a fresh ~1113 transactions + demo goals/festival rows.
