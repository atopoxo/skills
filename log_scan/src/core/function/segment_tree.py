from typing import List, Tuple, Optional

class SegmentTreeNode:
    def __init__(self, left: int, right: int, value: Optional[int]):
        self.left = left
        self.right = right
        self.value = value
        self.left_child = None
        self.right_child = None

class SegmentTree:
    def __init__(self, left: int, right: int, initial_value: Optional[int] = None):
        self.root = SegmentTreeNode(left, right, initial_value)

    def update(self, left: int, right: int, value: int) -> None:
        self._update_node(self.root, left, right, value)

    def get_range(self, left: int, right: int, value: int) -> List[Tuple[int, int]]:
        return self._query_node(self.root, left, right, value)

    def _update_node(self, node: SegmentTreeNode, left: int, right: int, value: int) -> None:
        if left == node.left and node.right == right:
            node.value = value
            node.left_child = None
            node.right_child = None
            return
        mid = (node.left + node.right) // 2
        self._push_down(node, mid)
        if right <= mid:
            self._update_node(node.left_child, left, right, value)
        elif left >= mid:
            self._update_node(node.right_child, left, right, value)
        else:
            self._update_node(node.left_child, left, mid, value)
            self._update_node(node.right_child, mid, right, value)
        self._update_node_value(node)

    def _push_down(self, node: SegmentTreeNode, mid: int) -> None:
        if not node.left_child and not node.right_child:
            node.left_child = SegmentTreeNode(node.left, mid, node.value)
            node.right_child = SegmentTreeNode(mid, node.right, node.value)
            node.value = None

    def _update_node_value(self, node: SegmentTreeNode) -> None:
        if node.left_child and node.right_child:
            if (node.left_child.value is not None and
                node.right_child.value is not None and
                node.left_child.value == node.right_child.value):
                self._update_node_value(node.left_child)
                self._update_node_value(node.right_child)
                node.value = node.left_child.value
                node.left_child = None
                node.right_child = None
            else:
                node.value = None

    def _query_node(self, node: SegmentTreeNode, left: int, right: int, value: int) -> List[Tuple[int, int]]:
        if node.value == value:
            return [(left, right)]
        left_res = []
        right_res = []
        mid = (node.left + node.right) // 2
        if right <= mid:
            if node.left_child:
                left_res = self._query_node(node.left_child, left, right, value)
            else:
                if node.value == value:
                    left_res = [(left, right)]
        elif left >= mid:
            if node.right_child:
                right_res = self._query_node(node.right_child, left, right, value)
            else:
                if node.value == value:
                    right_res = [(left, right)]
        else:
            if node.left_child:
                left_res = self._query_node(node.left_child, left, mid, value)
            else:
                if node.value == value:
                    left_res = [(left, mid)]
            if node.right_child:
                right_res = self._query_node(node.right_child, mid, right, value)
            else:
                if node.value == value:
                    right_res = [(mid, right)]
        return self._merge_ranges(left_res, right_res)

    def _merge_ranges(self, left_ranges: List[Tuple[int, int]], right_ranges: List[Tuple[int, int]]) -> List[Tuple[int, int]]:
        if len(left_ranges) == 0:
            return right_ranges
        if len(right_ranges) == 0:
            return left_ranges
        last_left = left_ranges[-1]
        first_right = right_ranges[0]
        if last_left[1] == first_right[0]:
            return left_ranges[:-1] + [(last_left[0], first_right[1])] + right_ranges[1:]
        else:
            return left_ranges + right_ranges