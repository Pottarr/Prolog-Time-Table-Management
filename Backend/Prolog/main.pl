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
