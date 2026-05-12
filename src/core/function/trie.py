from typing import TypeVar, Generic, Optional, List, Dict

T = TypeVar('T')

class TrieNode(Generic[T]):
    def __init__(self):
        self.children: Dict[str, TrieNode[T]] = {}
        self.value: Optional[T] = None

class Trie(Generic[T]):
    def __init__(self):
        self.root = TrieNode[T]()
    
    def insert(self, key: str, value: T) -> None:
        parts = [part for part in key.split('>') if part != '']
        current_node = self.root
        for part in parts:
            if part not in current_node.children:
                current_node.children[part] = TrieNode[T]()
            current_node = current_node.children[part]
        current_node.value = value
    
    def query(self, key: str) -> List[T]:
        parts = [part for part in key.split('>') if part != '']
        current_node = self.root
        for part in parts:
            if part not in current_node.children:
                return []
            current_node = current_node.children[part]
        
        results: List[T] = []
        self._collect_values(current_node, results)
        return results
    
    def _collect_values(self, node: TrieNode[T], results: List[T]) -> None:
        if node.value is not None:
            results.append(node.value)
        for child in node.children.values():
            self._collect_values(child, results)