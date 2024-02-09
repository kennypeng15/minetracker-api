# minetracker-api
---

(this README focuses on the API project only. for the write-up about MineTracker as a whole, 
see https://kennypeng15.github.io/projects/minetracker/index.html)

## Overview and Design
The (Flask) API for MineTracker.

Offers up GET endpoints that expose data about minesweeper.online games stored in DynamoDB.

Uses `boto3` to connect to AWS as needed, `flask` and `flask-cors` for endpoint and CORS handling, and `pandas` for
data manipulation. A `.env` file is used to mask secrets.

Is currently hosted on pythonanywhere.


## Available Endpoints
This API currently exposes 3 endpoints (all `GET`):
- `/`:
    - Provides a basic description of the API itself.
- `/status`:
    - Provides basic diagnostic information, namely, the cache's item count and refresh times.
- `/data`:
    - The primary data-exposing API. Use this endpoint to obtain information about minesweeper.online games.
    - Has several query parameters.
    - `solved`: one of [`true`, `false`], default `true`. Indicates if you want to receive only data about solved games.
    - `difficulty`: one of [`beginner`, `intermediate`, `expert`], default `expert`. Indicates which difficulty you want data about.
    - `3bv_threshold`: any positive integer. Defines the minimum Board 3BV for games you want data about.
    - `solved_percent_threshold`: any positive integer. Defines the minimum solved percentage for games you want data about.
    - `efficiency_threshold`: any positive integer. Defines the minimum efficiency for games you want data about.


## Caching
The data about minesweeper.online games stored in DynamoDB is very uniform and relational in nature - 
all entries have the same columns (see artifacts in `minetracker-migrator` / https://github.com/kennypeng15/minetracker-migrator, for example).
That being said, DynamoDB was chosen as the backing database rather than RDS since DynamoDB has 
an always-free offer, while RDS is only free tier for 12 months.

This leads to problems when deciding how to best retrieve data.

In DynamoDB, each entry must have a unique partition key, or entries can have the same partition key but a different sort key
(i.e., a unique partition key and sort key combination).
DynamoDB offers two ways of retrieving data: scans and queries. The scan operation scans through every row in a 
database. With the query operation, users can supply an equality condition for the partition key and
another condition (more flexible, e.g., `includes`, `geq`, etc.) for the sort key if a sort key is used; this means 
that DynamoDB only has to scan through certain partitions of data, which is potentially less expensive and more performant
than a scan.
DynamoDB cannot query on arbitrary (i.e., non-partition or sort key) attributes.

The data stored about minesweeper.online games takes the following format:
| game-id | game-timestamp | difficulty | elapsed-time | estimated-time | board-solved | completed-3bv | board-3bv | game-3bvps | useful-clicks | wasted-clicks | total-clicks | efficiency | solve-percentage |
| -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- | -- |
| 2358451094 | 2023-06-16 06:30:01+00:00 | expert | 20.503 | 79.338 | False | 46 | 178 | 2.2436 | 55 | 2 | 57 | 81.0 | 25.842696629213485 |

The only column that is guaranteed to be unique is `game-id`, essentially forcing `game-id` to be the partition key (and forcing
no sort key).
This means that queries such as "I want only expert `difficulty` games, with a `board-3bv` greater than 120" aren't possible
in DynamoDB, while they would be relatively easy using RDS and SQL.

This necessitates the use of the scan operation instead of query. Repeated scan operations (i.e., repeated full-database scans)
have the potential to both be slow and very cost-incurring, so a basic in-memory cache is used to speed up
delivery of API results and to avoid making repeated expensive calls to AWS.

When the API starts up, the cache is uninitialized and a "last request date" is set to sometime in the past.
When the first request to the `/data` endpoint is made, the API starts a full scan of the DynamoDB database
and stores the results of the database as an in-memory list, caching it.
The timestamp the scan was completed is stored.
Any filters passed in as query parameters are applied, and the user's desired subset of data is returned.

Now that the cache has been initialized, subsequent requests to `/data` will draw on that cached scan and 
will not actually result in AWS calls.
The cache has a lifetime of 24 hours, meaning 24 hours after the first request, another full scan of DynamoDB will
be initiated in AWS.

This caching approach was chosen since the entries in the database are extremely small, meaning a full scan of the database
returns only hundreds of kilobytes or a few megabytes of information; thus, the memory hit on the API is fairly manageable.

## Future Work and Potential Optimizations
Future work may involve seeing if list operations vs. pandas dataframe operations deliver faster results
on various data set sizes.