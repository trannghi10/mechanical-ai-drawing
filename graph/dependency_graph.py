"""Directed design relationships; graph edges do not infer missing CAD intent."""
import math
import networkx as nx


class DependencyGraph:
    def __init__(self):
        self.graph = nx.DiGraph()
        self.G = self.graph

    def add_part(self, part_id: str):
        self.graph.add_node(part_id)

    def add_dependency(self, source: str, target: str):
        self.graph.add_edge(source, target)

    def get_dependencies(self, part_id: str):
        return sorted(nx.descendants(self.graph, part_id), key=str)

    def get_direct_dependencies(self, part_id: str):
        return sorted(self.graph.successors(part_id), key=str)

    def topological_order(self, nodes=None):
        graph = self.graph if nodes is None else self.graph.subgraph(nodes)
        if not nx.is_directed_acyclic_graph(graph):
            raise ValueError('Quan hệ có vòng lặp; cần giải ràng buộc riêng')
        return list(nx.lexicographical_topological_sort(graph, key=str))


class DesignGraph(DependencyGraph):
    """Rigid translations in ONE common frame, with checked parent edges.

    Commands are proposals. The CAD adapter must validate hash/path/ownership.
    MaintainGap/AlignCenters need measured features and their own solvers.
    """
    def add_component(self, handle, comp_type):
        if not isinstance(handle, str) or not handle.strip():
            raise ValueError('Thiếu định danh chi tiết')
        self.graph.add_node(handle, type=comp_type)

    def add_constraint(self, source_handle, target_handle, constraint_type, value=0):
        if source_handle not in self.graph or target_handle not in self.graph:
            raise ValueError('Liên kết cần hai chi tiết đã được xác định')
        if constraint_type != 'rigid_attachment':
            raise ValueError('Quy tắc này cần bộ giải riêng và điểm/mặt lắp đã xác minh')
        if not math.isfinite(float(value)):
            raise ValueError('Giá trị liên kết phải hữu hạn')
        if self.graph.has_edge(source_handle, target_handle):
            raise ValueError('Quan hệ trùng lặp')
        self.graph.add_edge(source_handle, target_handle, constraint=constraint_type, gap=float(value))
        try:self.topological_order()
        except ValueError:
            self.graph.remove_edge(source_handle, target_handle)
            raise

    def propagate_change(self, modified_handle, delta_x, delta_y):
        if modified_handle not in self.graph:
            raise ValueError('Chi tiết thay đổi không nằm trong đồ thị')
        delta = (float(delta_x), float(delta_y))
        if not all(math.isfinite(v) for v in delta):
            raise ValueError('Dịch chuyển phải hữu hạn')
        reached = {modified_handle, *nx.descendants(self.graph, modified_handle)}
        order = self.topological_order(reached)
        motions = {modified_handle: delta}
        commands = []
        for target in order:
            proposals = []
            # A descendant need not have an edge from the modified root.
            # Parents outside the changed chain remain fixed anchors.
            for parent in self.graph.predecessors(target):
                if self.graph.edges[parent, target].get('constraint') != 'rigid_attachment':
                    raise ValueError('Liên kết chưa có bộ giải được kiểm chứng')
                proposals.append(motions.get(parent, (0., 0.)))
            if target == modified_handle:
                proposals.append(delta)
            expected = proposals[0]
            if any(not all(math.isclose(a, b, rel_tol=0, abs_tol=1e-8)
                           for a, b in zip(expected, proposal)) for proposal in proposals[1:]):
                raise ValueError('Các liên kết yêu cầu dịch chuyển xung đột tại '+target)
            motions[target] = expected
            if target != modified_handle and any(abs(v) >= 1e-8 for v in expected):
                commands.append(dict(Handle=target, Action='Move', DeltaX=expected[0], DeltaY=expected[1]))
        return commands
