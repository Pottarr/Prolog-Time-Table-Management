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
