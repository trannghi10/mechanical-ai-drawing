"""Lightweight pure-python graph utilities compatible with basic NetworkX DiGraph operations."""
from collections import defaultdict, deque


class DiGraph:
    def __init__(self):
        self._nodes = set()
        self._succ = defaultdict(set)
        self._pred = defaultdict(set)

    def add_node(self, node):
        self._nodes.add(node)

    def add_nodes_from(self, nodes):
        for n in nodes:
            self._nodes.add(n)

    def add_edge(self, u, v):
        self._nodes.add(u)
        self._nodes.add(v)
        self._succ[u].add(v)
        self._pred[v].add(u)

    def predecessors(self, n):
        return list(self._pred.get(n, ()))

    def successors(self, n):
        return list(self._succ.get(n, ()))

    def to_undirected(self):
        u = UndirectedGraph()
        u.add_nodes_from(self._nodes)
        for parent, children in self._succ.items():
            for child in children:
                u.add_edge(parent, child)
        return u


class UndirectedGraph:
    def __init__(self):
        self._nodes = set()
        self._adj = defaultdict(set)

    def add_nodes_from(self, nodes):
        for n in nodes:
            self._nodes.add(n)

    def add_edge(self, u, v):
        self._nodes.add(u)
        self._nodes.add(v)
        self._adj[u].add(v)
        self._adj[v].add(u)


def descendants(graph, source):
    """Return all nodes reachable from source in graph."""
    visited = set()
    queue = deque([source])
    while queue:
        curr = queue.popleft()
        for succ in graph.successors(curr):
            if succ not in visited:
                visited.add(succ)
                queue.append(succ)
    return visited


def strongly_connected_components(graph):
    """Tarjan's algorithm for strongly connected components."""
    index = 0
    indices = {}
    lowlink = {}
    stack = []
    on_stack = set()
    sccs = []

    def strongconnect(v):
        nonlocal index
        indices[v] = index
        lowlink[v] = index
        index += 1
        stack.append(v)
        on_stack.add(v)

        for w in graph.successors(v):
            if w not in indices:
                strongconnect(w)
                lowlink[v] = min(lowlink[v], lowlink[w])
            elif w in on_stack:
                lowlink[v] = min(lowlink[v], indices[w])

        if lowlink[v] == indices[v]:
            scc = set()
            while True:
                w = stack.pop()
                on_stack.remove(w)
                scc.add(w)
                if w == v:
                    break
            sccs.append(scc)

    for node in graph._nodes:
        if node not in indices:
            strongconnect(node)
    return sccs


def node_connected_component(graph, n):
    """Return all nodes in the connected component of n in an undirected graph."""
    visited = set([n])
    queue = deque([n])
    while queue:
        curr = queue.popleft()
        for neighbor in graph._adj.get(curr, ()):
            if neighbor not in visited:
                visited.add(neighbor)
                queue.append(neighbor)
    return visited
