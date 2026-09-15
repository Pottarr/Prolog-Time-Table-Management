# Prolog Time Table Management — SWI-Prolog Docker Backend Setup

## 1. Project Goal

The goal of this project is to build a **classroom timetable and room-management system** whose scheduling/constraint logic is handled by **SWI-Prolog**.

The eventual system should be able to receive course information such as dates, times, room requirements, and other constraints, then use Prolog to find a valid assignment. A particularly important optimization goal is to **use as few classrooms as possible**, leaving unused rooms available for other activities.

The intended architecture separates the normal web application from the Prolog reasoning engine:

```text
Frontend
   |
   v
Main Backend / API
   |
   | HTTP + JSON
   v
SWI-Prolog Service
   |
   | Rules + constraints + optimization
   v
Timetable / room assignment
```

The SWI-Prolog service can live in its own Docker container. Later, another backend container can act as the public API/application backend and communicate with Prolog over Docker's internal network.

For now, we built a small proof of concept using a family relationship rule such as `parent(alice, bob)` to verify that:

```text
HTTP request -> Docker -> SWI-Prolog -> Prolog rule -> JSON response
```

works correctly before implementing the real timetable solver.

---

## 2. Current File Hierarchy

The current Prolog backend directory looks like this:

```text
Backend/
└── Prolog/
    ├── Dockerfile
    ├── main.pl
    └── scheduler.pl
```

The important files are:

```text
Dockerfile    -> Builds the SWI-Prolog container.
main.pl       -> Starts the HTTP server and defines API handlers.
scheduler.pl  -> Contains Prolog facts and rules.
```

Later, the project could grow into something like:

```text
Prolog-Time-Table-Management/
├── Backend/
│   ├── API/
│   │   ├── Dockerfile
│   │   └── ...
│   └── Prolog/
│       ├── Dockerfile
│       ├── main.pl
│       ├── scheduler.pl
│       ├── constraints.pl
│       └── rooms.pl
├── Frontend/
│   └── ...
└── compose.yml
```

---

## 3. Dockerfile

The Dockerfile uses the official SWI-Prolog image, copies the Prolog application into the container, and starts `main.pl`.

```dockerfile
FROM swipl:latest

WORKDIR /app

COPY . .

EXPOSE 8080

CMD ["swipl", "-q", "-s", "main.pl", "-g", "start"]
```

### Explanation

This line selects an image containing SWI-Prolog:

```dockerfile
FROM swipl:latest
```

This sets `/app` as the working directory inside the container:

```dockerfile
WORKDIR /app
```

This copies the files from the current Docker build context into `/app`:

```dockerfile
COPY . .
```

This documents that the application listens on TCP port 8080:

```dockerfile
EXPOSE 8080
```

Finally, this starts SWI-Prolog:

```dockerfile
CMD ["swipl", "-q", "-s", "main.pl", "-g", "start"]
```

The options mean:

```text
-q          -> Quiet startup.
-s main.pl  -> Load main.pl.
-g start    -> Execute the Prolog goal start/0 after loading the file.
```

---

## 4. `scheduler.pl`

For the proof of concept, `scheduler.pl` contains a tiny family knowledge base rather than timetable rules.

```prolog
% Facts
parent(alice, bob).
parent(alice, charlie).
parent(bob, david).
parent(bob, eve).
parent(charlie, frank).

% Rules

% X is a grandparent of Z if:
% X is parent of Y AND Y is parent of Z.
grandparent(X, Z) :-
    parent(X, Y),
    parent(Y, Z).

% Two people are siblings if they share a parent.
sibling(X, Y) :-
    parent(P, X),
    parent(P, Y),
    X \= Y.

% Recursive ancestor rule
ancestor(X, Y) :-
    parent(X, Y).

ancestor(X, Y) :-
    parent(X, Z),
    ancestor(Z, Y).
```

### Facts

A statement such as:

```prolog
parent(alice, bob).
```

means that Alice is a parent of Bob.

These are direct facts stored in the Prolog knowledge base.

### Grandparent Rule

```prolog
grandparent(X, Z) :-
    parent(X, Y),
    parent(Y, Z).
```

This means:

```text
X is a grandparent of Z
IF
X is a parent of Y
AND
Y is a parent of Z.
```

For example:

```prolog
parent(alice, bob).
parent(bob, david).
```

allows Prolog to infer:

```prolog
grandparent(alice, david).
```

### Sibling Rule

```prolog
sibling(X, Y) :-
    parent(P, X),
    parent(P, Y),
    X \= Y.
```

Two people are considered siblings when they share a parent and are not the same person.

### Recursive Ancestor Rule

The first rule handles direct parent relationships:

```prolog
ancestor(X, Y) :-
    parent(X, Y).
```

The second recursively walks through the family tree:

```prolog
ancestor(X, Y) :-
    parent(X, Z),
    ancestor(Z, Y).
```

Therefore Prolog can infer relationships across multiple generations.

---

## 5. `main.pl`

`main.pl` turns the Prolog program into a small HTTP service.

```prolog
:- use_module(library(http/thread_httpd)).
:- use_module(library(http/http_dispatch)).
:- use_module(library(http/http_parameters)).
:- use_module(library(http/http_json)).

:- consult('scheduler.pl').

:- http_handler(root(parent), parent_handler, []).

start :-
    http_server(http_dispatch, [port(8080)]),
    thread_get_message(_).

parent_handler(Request) :-
    http_parameters(Request, [
        parent(Parent, [atom]),
        child(Child, [atom])
    ]),

    ( parent(Parent, Child) ->
        Result = true
    ;
        Result = false
    ),

    reply_json_dict(_{
        parent: Parent,
        child: Child,
        result: Result
    }).
```

### HTTP Libraries

These lines import SWI-Prolog's HTTP functionality:

```prolog
:- use_module(library(http/thread_httpd)).
:- use_module(library(http/http_dispatch)).
:- use_module(library(http/http_parameters)).
:- use_module(library(http/http_json)).
```

They provide the HTTP server, routing, query-parameter parsing, and JSON response functionality.

### Loading the Rules

```prolog
:- consult('scheduler.pl').
```

This loads the facts and rules from `scheduler.pl` into the application.

Because of this, `main.pl` can execute predicates such as:

```prolog
parent(alice, bob).
```

### Registering the Endpoint

```prolog
:- http_handler(root(parent), parent_handler, []).
```

This connects the HTTP path:

```text
/parent
```

to the Prolog predicate:

```prolog
parent_handler/1
```

### Starting the Server

```prolog
start :-
    http_server(http_dispatch, [port(8080)]),
    thread_get_message(_).
```

The first line starts the HTTP server on port 8080:

```prolog
http_server(http_dispatch, [port(8080)])
```

The following line keeps the main Prolog process alive:

```prolog
thread_get_message(_).
```

This was important during testing. Without keeping the process alive, the Docker container could finish its startup goal and exit, leaving nothing listening on port 8080.

### Reading HTTP Parameters

The handler expects two query parameters:

```prolog
http_parameters(Request, [
    parent(Parent, [atom]),
    child(Child, [atom])
])
```

For example, this HTTP request:

```text
/parent?parent=alice&child=bob
```

produces values equivalent to:

```prolog
Parent = alice,
Child = bob.
```

### Asking Prolog the Question

The handler then evaluates:

```prolog
parent(Parent, Child)
```

using:

```prolog
( parent(Parent, Child) ->
    Result = true
;
    Result = false
)
```

If the fact/rule succeeds, the result is `true`; otherwise it is `false`.

### Returning JSON

Finally:

```prolog
reply_json_dict(_{
    parent: Parent,
    child: Child,
    result: Result
}).
```

returns an HTTP JSON response.

For the Alice/Bob example, the response is:

```json
{
  "child": "bob",
  "parent": "alice",
  "result": true
}
```

---

## 6. Building the Docker Image

From the directory containing the Dockerfile, build the image with:

```bash
docker build -t prolog-test .
```

The final dot is important:

```text
.
```

It tells Docker to use the current directory as the build context.

During debugging, we also rebuilt without using cached layers:

```bash
docker build --no-cache -t prolog-test .
```

This is useful after modifying `main.pl` when you want to make absolutely sure the latest files are copied into the image.

---

## 7. Running the Container

The basic run command is:

```bash
docker run --rm -p 8080:8080 prolog-test
```

For debugging, we used a named container without `--rm`:

```bash
docker run --name prolog-debug -p 8080:8080 prolog-test
```

The port mapping:

```text
8080:8080
```

means:

```text
Host port 8080 -> Container port 8080
```

Therefore the Prolog HTTP service is reachable from the host at:

```text
http://localhost:8080
```

---

## 8. Checking Whether the Container Is Running

We verified the container with:

```bash
docker ps
```

The successful result showed the `prolog-test` image running and exposing port 8080:

```text
CONTAINER ID   IMAGE         COMMAND                  STATUS          PORTS                                         NAMES
36077d2c4a5e   prolog-test   "swipl -q -s main.pl…"   Up              0.0.0.0:8080->8080/tcp, [::]:8080->8080/tcp   prolog-debug
```

If a named debug container already exists, it can be removed with:

```bash
docker rm -f prolog-debug
```

Container logs can be inspected with:

```bash
docker logs prolog-debug
```

---

## 9. Sending the First Query

With the container running, we sent an HTTP request from another terminal:

```bash
curl "http://localhost:8080/parent?parent=alice&child=bob"
```

The service successfully returned:

```json
{"child":"bob","parent":"alice","result":true}
```

This proves that the complete path works:

```text
curl
  |
  | HTTP GET
  v
localhost:8080
  |
  | Docker port forwarding
  v
SWI-Prolog container
  |
  v
main.pl
  |
  | parent(alice, bob)
  v
scheduler.pl
  |
  | fact succeeds
  v
true
  |
  v
JSON response
```

A false query can also be tested:

```bash
curl "http://localhost:8080/parent?parent=bob&child=alice"
```

Since the knowledge base does not contain that relationship, the expected result is:

```json
{
  "child": "alice",
  "parent": "bob",
  "result": false
}
```

---

## 10. Why We Do Not Expose Arbitrary Prolog Queries

It may be tempting to create an endpoint like:

```text
/query?q=parent(alice,bob)
```

and execute whatever Prolog expression the caller supplies.

That should **not** be the normal design because it effectively exposes a remote Prolog interpreter. Instead, the HTTP layer should expose specific operations such as:

```text
/parent
/schedule
/check-room
/generate-timetable
```

and each handler should invoke only predicates that the application intentionally allows.

The general pattern is therefore:

```text
Untrusted HTTP input
        |
        v
Validate / parse parameters
        |
        v
Call known Prolog predicate
        |
        v
Return controlled JSON output
```

---

## 11. How This Becomes the Real Timetable Project

The current family rules are only a connectivity test.

Eventually:

```prolog
parent(alice, bob).
```

will be replaced by facts representing courses, rooms, times, capacities, and other scheduling information.

Conceptually, the knowledge base might contain facts such as:

```prolog
room(r101, 30).
room(r102, 50).
room(r103, 100).

course(coa, 40).
course(dsa, 25).
```

The system can then define constraints such as:

```text
A room cannot contain two simultaneous classes.
A room must have enough capacity for the course.
A laboratory course must use an appropriate laboratory.
A lecturer cannot teach two simultaneous classes.
A student group cannot attend two simultaneous classes.
Unavailable rooms cannot be assigned.
```

The optimization objective is then:

```text
Find a valid timetable while using the minimum number of rooms.
```

This lets the university reserve the remaining rooms for meetings, events, examinations, maintenance, or other purposes.

SWI-Prolog's constraint programming facilities, particularly `library(clpfd)`, can later be used to model these scheduling constraints and optimization objectives.

---

## 12. Intended Two-Container Architecture

The final backend can use two separate containers:

```text
                     Internet / Frontend
                            |
                            v
                 +---------------------+
                 | Main Backend / API  |
                 | Rust / Java / Go    |
                 |                     |
                 | Auth                |
                 | Validation          |
                 | Database access     |
                 | Application logic   |
                 +----------+----------+
                            |
                            | Internal HTTP + JSON
                            v
                 +---------------------+
                 | SWI-Prolog Service  |
                 |                     |
                 | Facts               |
                 | Rules               |
                 | CLP(FD) constraints |
                 | Optimization        |
                 +---------------------+
```

Only the main backend needs to be exposed publicly. The Prolog service can remain accessible only through the internal Docker network.

A future Compose file could look conceptually like this:

```yaml
services:
  backend:
    build: ./Backend/API
    ports:
      - "8080:8080"
    depends_on:
      - prolog

  prolog:
    build: ./Backend/Prolog
    expose:
      - "8081"
```

Inside the Docker network, the backend could communicate with Prolog using the service hostname:

```text
http://prolog:8081
```

The Prolog service therefore acts as a dedicated **reasoning and constraint-solving engine**, while the normal backend remains responsible for the rest of the web application.

---

## 13. Current Milestone

The proof of concept is now successful.

We have confirmed all of the following:

```text
[OK] SWI-Prolog runs inside Docker.
[OK] Docker copies the Prolog source files into the image.
[OK] main.pl loads scheduler.pl.
[OK] SWI-Prolog starts an HTTP server.
[OK] The container remains alive while serving requests.
[OK] Port 8080 is forwarded from the host to the container.
[OK] HTTP query parameters reach Prolog.
[OK] Prolog evaluates a fact/rule.
[OK] The result is converted into JSON.
[OK] curl receives the JSON response.
```

The working test request is:

```bash
curl "http://localhost:8080/parent?parent=alice&child=bob"
```

with the successful response:

```json
{"child":"bob","parent":"alice","result":true}
```

The next major milestone is to replace the family example with the first real timetable model: **course time intervals + available rooms + collision constraints + minimum-room optimization**.
