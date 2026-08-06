"""The admin console: two queues and a person to decide them.

**Why it is served by the API rather than built as its own app.**

Every rule that makes a decision safe lives in `api/v1/review.py` — a rejection
needs a reason the author can read, one decision closes every open report on the
same food, and the numbers on a USDA row cannot be corrected in place because
`source`/`source_id` say where they came from. None of that is a database
constraint. A hand-written UPDATE in Supabase Studio walks past all of it, and so
would any admin tool that talked to Postgres directly.

So this console has no privileged access at all. It signs in with an ordinary
admin account and calls exactly the endpoints the phone calls, which means it
cannot do anything the API would refuse — and any rule added there applies here
without a second implementation to keep in step.

**Why not a separate deployment.** One HTML file rides along with a backend that
has to be deployed anyway: no second build, no second auth flow, and no CORS,
because it is the same origin. It is also deletable in one commit if it ever
outgrows a single page.

**Not in the mobile app, deliberately.** Admin tooling does not belong in a
binary every user installs; a client that cannot call the decision endpoints is
one that cannot be tricked into calling them.

**What serving this page costs.** The admin *endpoints* answer 404 rather than
403 for non-admins, so the surface is not mappable by probing. Serving this page
publicly gives that back a little: anybody can see a login form exists. The lock
is unchanged — the page holds no data and does nothing until the API accepts an
admin token — but the door is now visible. Set `ADMIN_UI_ENABLED=false` to remove
it entirely; the API keeps working and Supabase Studio's views remain readable.
"""
