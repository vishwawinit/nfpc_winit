# NFPC Reports Project Rules

## CRITICAL: Source Database Safety
- The MSSQL source database (20.203.45.86 / NFPCsfaV3_070326) is a LIVE PRODUCTION database
- **READ-ONLY ACCESS ONLY** - NEVER execute INSERT, UPDATE, DELETE, DROP, ALTER, CREATE, or any write/modify operations on the source MSSQL database
- Only SELECT queries are permitted against the source
- All write operations go to the LOCAL PostgreSQL reporting database only
