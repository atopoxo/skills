import re
from typing import Dict, List, Set, Optional, Any
from core.ai_model.base.ai_types import ContextTreeNode
from core.types.scope import Scope
from core.context.lua.lua_context_base import LuaContextBase, DependencyGraphType, DefinitionMapType, ScopeNode

class LuaContext(LuaContextBase):
    def __init__(self):
        super().__init__()

    def build_tree(self, context_tree: Optional[ContextTreeNode], scope_node: ScopeNode, 
                   root: Any, content: str, start_pos: int):
        def traverse(parent_tree: Optional[ContextTreeNode], current: Any, statement: Any, is_local: bool):
            is_local_function = self._is_local_function(scope_node, current)
            if is_local_function:
                self._enter_new_scope(None, None, parent_tree, scope_node, current, content, start_pos, statement, True)
            current_tree = self._process_node_for_dependencies(None, None, parent_tree, scope_node, current, content, start_pos, statement, None, is_local)
            filters = self.filters.get(current.type, [])
            if (len(filters) == 0 or '*' not in filters) and current.children:
                child_local = False
                for child in current.children:
                    if child.type == 'local':
                        child_local = True
                    if child.type not in filters:
                        if child_local is False:
                            child_local = False if self._is_local_region(current, child.type) else is_local
                        if self._is_scope_node(current, child.type):
                            self._enter_new_scope(None, None, parent_tree, scope_node, current, content, start_pos, statement)
                        traverse(current_tree, child, statement, child_local)
                        if self._is_scope_node(current, child.type):
                            self._exit_scope(scope_node)
            if is_local_function:
                self._exit_scope(scope_node)
        traverse(context_tree, root, None, False)
    
    def build_dependency_graph(self, definition_map: DefinitionMapType, 
                               dependency_graph: DependencyGraphType, 
                               scope_node: ScopeNode, root: Any, 
                               content: str, start_pos: int):
        def traverse(current: Any, statement: Any, parent_type: Any, is_local: bool):
            try:
                if self._is_range_change(current, None):
                    statement = current
                is_local_function = self._is_local_function(scope_node, current)
                if is_local_function:
                    self._enter_new_scope(definition_map, dependency_graph, None, scope_node, current, content, start_pos, statement, True)
                filters = self.filters.get(current.type, [])
                if (len(filters) == 0 or '*' not in filters) and current.children:
                    child_local = False
                    for child in current.children:
                        if child.type == 'local':
                            child_local = True
                        if child.type not in filters:
                            if child_local is False:
                                child_local = False if self._is_local_region(current, child.type) else is_local
                            if self._is_scope_node(current, child.type):
                                self._enter_new_scope(definition_map, dependency_graph, None, scope_node, current, content, start_pos, statement)
                            if child.type == 'identifier':
                                child_parent_type = current.type
                            else:
                                child_parent_type = child.type
                            traverse(child, statement, child_parent_type, child_local)
                            if self._is_scope_node(current, child.type):
                                self._exit_scope(scope_node)
                self._process_node_for_dependencies(definition_map, dependency_graph, None, scope_node, current, content, start_pos, statement, parent_type, is_local)
                if is_local_function:
                    self._exit_scope(scope_node)
            except Exception as ex:
                print(f"Error processing node {current.type} at {current.start_pos}: {ex}")
        traverse(root, None, root.type, False)
    
    def is_valid_global_string(self, content: str) -> bool:
        regex = r'^global>[^>]+$'
        return bool(re.fullmatch(regex, content))
    
    def _process_node_for_dependencies(self, definition_map: Optional[DefinitionMapType],
                                       dependency_graph: Optional[DependencyGraphType],
                                       keyword_tree: Optional[ContextTreeNode],
                                       scope_node: ScopeNode, current: Any,
                                       content: str, start_pos: int,
                                       statement: Any, parent_type: Any, is_local: bool) -> Optional[ContextTreeNode]:
        context_tree = keyword_tree
        node_type = current.type
        try:
            if node_type == 'identifier':
                context_tree = self._process_identifier_dependencies(
                    definition_map, dependency_graph, keyword_tree, scope_node,
                    current, content, start_pos, statement, parent_type, is_local
                )
            elif node_type == 'variable_list':
                context_tree = self._process_variable_list_dependencies(
                    definition_map, dependency_graph, keyword_tree, scope_node,
                    current, content, start_pos, statement, parent_type, is_local
                )
            elif node_type == 'dot_index_expression':
                context_tree = self._process_member_dependencies(
                    definition_map, dependency_graph, keyword_tree, scope_node,
                    current, content, start_pos, statement, parent_type, is_local
                )
            elif node_type == 'function_call':
                context_tree = self._process_call_dependencies(
                    definition_map, dependency_graph, keyword_tree, scope_node,
                    current, content, start_pos, statement
                )
            elif node_type in ['function_declaration']:
                context_tree = self._process_function_dependencies(
                    definition_map, dependency_graph, keyword_tree, scope_node,
                    current, content, start_pos, statement
                )
            elif node_type == 'assignment_statement':
                context_tree = self._process_assignment_dependencies(
                    definition_map, dependency_graph, keyword_tree, scope_node,
                    current, content, start_pos, statement, is_local
                )
        except Exception as e:
            print(f"Error processing node {node_type}: {e}")
        return context_tree