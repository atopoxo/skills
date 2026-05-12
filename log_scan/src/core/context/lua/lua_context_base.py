from typing import Dict, List, Set, Optional, Any
from dataclasses import dataclass, field
from core.ai_model.base.ai_types import ContextItem, ContextTreeNode
from core.types.scope import Scope
from core.context.base.context_base import ContextBase

DependencyGraphType = Dict[str, Set[str]]
DefinitionMapType = Dict[str, 'ContextItem']

@dataclass
class ScopeNode:
    stack: List[Dict[str, Scope]] = field(default_factory=list)
    current_depth: int = 0
    current: Optional[Scope] = None
    file_path: str = ""

class LuaContextBase(ContextBase):
    def __init__(self):
        super().__init__()
        self.__init_filters()

    def __init_filters(self):
        types = [
            'variable_list',
            'assignment_statement',
            'function_declaration',
            'variable_declaration',
            'for_statement',
            'do_statement',
            'if_statement',
            'elseif_statement',
            'else_statement',
            'for_numeric_clause',
            'for_generic_clause',
            'while_statement',
            'repeat_statement',
            'return_statement',
            'parameters',
            'arguments',
            'dot_index_expression',
            'function_call'
        ]
        self.filters: Dict[str, Set[str]] = {}
        for type_name in types:
            match type_name:
                case 'variable_list':
                    self.filters[type_name] = frozenset(['identifier'])
                case 'assignment_statement':
                    self.filters[type_name] = frozenset(['variable_list', '='])
                case 'function_declaration':
                    self.filters[type_name] = frozenset(['comment', 'local', 'function', 'identifier'])
                case 'variable_declaration':
                    self.filters[type_name] = frozenset(['comment', 'local'])
                case 'for_statement':
                    self.filters[type_name] = frozenset(['for', 'do', 'end'])
                case 'do_statement':
                    self.filters[type_name] = frozenset(['do', 'end'])
                case 'if_statement':
                    self.filters[type_name] = frozenset(['if', 'then', 'end'])
                case 'elseif_statement':
                    self.filters[type_name] = frozenset(['elseif', 'then'])
                case 'else_statement':
                    self.filters[type_name] = frozenset(['else'])
                case 'for_numeric_clause':
                    self.filters[type_name] = frozenset([])
                case 'for_generic_clause':
                    self.filters[type_name] = frozenset(['in'])
                case 'while_statement':
                    self.filters[type_name] = frozenset(['while', 'do', 'end'])
                case 'repeat_statement':
                    self.filters[type_name] = frozenset(['repeat', 'until'])
                case 'return_statement':
                    self.filters[type_name] = frozenset(['return', ';'])
                case 'parameters' | 'arguments':
                    self.filters[type_name] = frozenset(['(', ')'])
                case 'dot_index_expression':
                    self.filters[type_name] = frozenset(['identifier', '.'])
                case 'function_call':
                    self.filters[type_name] = frozenset([])
                case _:
                    self.filters[type_name] = frozenset(['*'])

    def _enter_new_scope(self, definition_map: Optional[DefinitionMapType],
                        dependency_graph: Optional[DependencyGraphType],
                        context_tree: Optional[ContextTreeNode],
                        scope_node: ScopeNode, current: Any,
                        content: str, start_pos: int,
                        statement: Any, is_file_local: bool = False):
        scope_type = 'block' if self._is_block_scope_node(current) else 'function'
        scope_name = scope_node.file_path if is_file_local else self._get_scope_name(current, start_pos, scope_type)
        scope_node.current_depth += 1
        if scope_node.current_depth >= len(scope_node.stack):
            new_scopes: Dict[str, Scope] = {}
            scope_node.stack.append(new_scopes)
        new_scopes = scope_node.stack[scope_node.current_depth]
        new_scope = new_scopes.get(scope_name)
        if not new_scope:
            new_scope = Scope(scope_name, scope_node.current, scope_type == 'block')
            new_scopes[scope_name] = new_scope
        scope_node.current = new_scope
        if scope_type == 'block':
            self._process_block_scope_variables(definition_map, dependency_graph, context_tree, scope_node, current, content, start_pos, statement)

    def _exit_scope(self, scope_node: ScopeNode):
        if len(scope_node.stack) > 1:
            if scope_node.current:
                scope_node.current = scope_node.current.parent
            scope_node.current_depth -= 1

    def _get_scope_name(self, node: Any, start_pos: int, scope_type: str) -> str:
        scope_name = ''
        start = node.start_byte + start_pos
        end = node.end_byte + start_pos
        if scope_type == 'function':
            for child in node.children:
                if child.type == 'identifier':
                    func_name = self._get_function_name(child)
                    scope_name = func_name if func_name else f"{start}~{end}"
                    break
        else:
            scope_name = f"{start}~{end}"
        return scope_name
    
    def _get_scoped_name(self, name: str, scope_node: ScopeNode) -> str:
        parent_name = f"{scope_node.current.full_name}" if scope_node.current else ""
        return f"{parent_name}>{name}"
    
    def _create_tree_node(self, keyword_tree: Optional[ContextTreeNode],
                         scope_node: ScopeNode, current: Any,
                         content: str, start_pos: int,
                         statement: Any, name: str,
                         scoped_name: str) -> Optional[ContextTreeNode]:
        context_item = self._create_context_item_for_lua(current, current.type, scoped_name, False, None, content, start_pos, statement)
        context_tree_node = ContextTreeNode(
            value=context_item,
            children=[]
        )
        if keyword_tree:
            keyword_tree['children'].append(context_tree_node)
        if scope_node.current:
            scope_node.current.add_variable(name, scoped_name, False)
        return context_tree_node
    
    def _create_context_item_for_lua(self, node: Any, type_str: str, parent_name: str, need_range: bool, name: Optional[str], content: str, start_pos: int, statement: Optional[Any] = None) -> ContextItem:
        if statement:
            start, end = statement.start_byte, statement.end_byte
        else:
            start, end = node.range.start_byte + start_pos, node.range.end_byte + start_pos
        if need_range:
            parent_name = f"{parent_name}>{start}~{end}"
        final_name = f"{parent_name}>{name}" if name else parent_name
        result: ContextItem = {
            "type": type_str,
            "name": final_name,
            "range": {"start": start, "end": end}
        }
        return result
    
    def _is_scope_node(self, node: Any, key: str) -> bool:
        node_type = node.type
        if node_type in ['function_declaration']:
            return key != 'parameters'
        else:
            return self._is_block_scope_node(node)
        
    def _is_local_region(self, node: Any, key: str) -> bool:
        node_type = node.type
        if node_type in ['function_declaration']:
            return key != 'parameters'
        elif node_type in ['expression_list']:
            return True
        else:
            return self._is_block_scope_node(node)
        
    def _is_block_scope_node(self, node: Any) -> bool:
        block_types = [
            'do_statement',         # do...end 块
            'if_statement',         # if 语句块
            'for_statement',        # 数值 for 循环
            'while_statement',      # while 循环
            'repeat_statement'      # repeat...until 循环
        ]
        if node.type in block_types:
            return True
        else:
            return False
        # return node.type in block_types

    def _check_define_node(self, definition_map: DefinitionMapType,
                          scope_node: ScopeNode, current: Any,
                          content: str, start_pos: int,
                          statement: Any, name: str,
                          scoped_name: str, change: bool = False):
        if scoped_name not in definition_map:
            item = self._create_context_item_for_lua(current, current.type, scoped_name, False, None, content, start_pos, statement)
            definition_map[scoped_name] = item
        if scope_node.current:
            scope_node.current.add_variable(name, scoped_name, change)

    def _is_range_change(self, current: Any, parent_type: str) -> bool:
        if current:
            if (self._is_scope_node(current, '') or current.type in ['variable_declaration', 'assignment_statement', 'identifier']):
                return True
            else:
                return False
        else:
            if parent_type in ['variable_declaration', 'assignment_statement']:
                return True
            else:
                return False
        
    def _is_local_function(self, scope_node: ScopeNode, node: Any) -> bool:
        if scope_node.current_depth == 0:
            node_type = node.type
            return (node_type in ['function_declaration'] and node.children and node.children[0].type == 'local')
        else:
            return False
        
    def _get_function_name(self, node: Any, declare: bool = False) -> Optional[str]:
        if not node:
            return None
        node_type = node.type
        if node_type == 'identifier':
            return node.text.decode('utf8')
        elif node_type == 'dot_index_expression':
            name = self._get_function_name(node.children[0], declare)
            if declare and node.children[0].type == 'identifier':
                name = f"{name}-{node.start_byte}"
            return f"{name}>{self._get_function_name(node.children[2])}"
        elif node_type == 'function_call':
            for child in node.children:
                if child.type in ['arguments']:
                    continue
                return self._get_function_name(child)
        else:
            return None

    def _collect_dependencies_from_expression(self, definition_map: Optional[DefinitionMapType],
                                             dependency_graph: Optional[DependencyGraphType],
                                             keyword_tree: Optional[ContextTreeNode],
                                             dependencies: Set[str],
                                             scope_node: ScopeNode, node: Any,
                                             content: str, start_pos: int,
                                             statement: Any, deep: bool = False):
        if not node:
            return
        is_block_node = self._is_block_scope_node(node)
        if is_block_node:
            self._enter_new_scope(definition_map, dependency_graph, keyword_tree, scope_node, node, content, start_pos, statement)
        
        node_type = node.type
        if node_type == 'identifier':
            name = node.text.decode('utf8')
            if name:
                if deep:
                    scoped_func_name = self._resolve_scoped_name(scope_node, name, node)
                else:
                    scoped_func_name = f"{self._get_scoped_name(name, scope_node)}-{node.start_byte}"
                dependencies.add(scoped_func_name)
        elif node_type == 'function_call':
            name = self._get_function_name(node.children[0])
            if name:
                scoped_name = ''
                base = node.children[0]
                if base.type == 'dot_index_expression':
                    scoped_name = self._get_scoped_name(self._get_function_name(base, True), scope_node)
                else:
                    scoped_name = f"{self._get_scoped_name(name, scope_node)}-{node.start_byte}"
                if deep:
                    func_declare_name = self._resolve_scoped_name(scope_node, name, node)
                else:
                    func_declare_name = scoped_name
                dependencies.add(func_declare_name)
        elif node_type == 'dot_index_expression':
            name = self._get_function_name(node, True)
            if name:
                scoped_func_name = self._get_scoped_name(name, scope_node)
                dependencies.add(scoped_func_name)
        elif node_type in ['string', 'number', 'bool']:
            name = node_type
            dependencies.add(name)
        elif node_type == 'table_constructor':
            has_valid_field = False
            if node.children:
                for child in node.children:
                    if child.type == 'field':
                        for field in child.children:
                            if field.type in ['[', ']', '=']:
                                continue
                            self._collect_dependencies_from_expression(definition_map, dependency_graph, keyword_tree, dependencies, scope_node, field, content, start_pos, statement, deep)
                            has_valid_field = True
            if has_valid_field is False:
                name = node_type
                dependencies.add(name)
        elif node_type == 'binary_expression':
            if node.children:
                for child in node.children:
                    if child.type in ['+', '-', '*', '/']:
                        continue
                    self._collect_dependencies_from_expression(definition_map, dependency_graph, keyword_tree, dependencies, scope_node, child, content, start_pos, statement, deep)
        elif node_type == 'unary_expression':
            if node.children:
                for child in node.children:
                    if child.type in ['not', '-']:
                        continue
                    self._collect_dependencies_from_expression(definition_map, dependency_graph, keyword_tree, dependencies, scope_node, child, content, start_pos, statement, deep)
        elif node_type == 'assignment_statement':
            scoped_name = ''
            if node.children and len(node.children) == 3 and node.children[0].type == 'variable_list':
                variables = node.children[0].children
                for variable in variables:
                    var_type = variable.type
                    if var_type == 'identifier':
                        name = variable.text.decode('utf8')
                        scoped_name = f"{self._get_scoped_name(name, scope_node)}-{node.start_byte}"
                        dependencies.add(scoped_name)
                    elif var_type == 'dot_index_expression':
                        name = self._get_function_name(variable)
                        if name:
                            scoped_name = self._get_scoped_name(self._get_function_name(variable, True), scope_node)
                            dependencies.add(scoped_name)
        else:
            for child in node.children:
                self._collect_dependencies_from_expression(definition_map, dependency_graph, keyword_tree, dependencies, scope_node, child, content, start_pos, statement, deep)
        if is_block_node:
            self._exit_scope(scope_node)

    def _resolve_scoped_name(self, scope_node: ScopeNode, name: str, node: Any) -> str:
        if scope_node.current and scope_node.current.has_variable(name):
            scoped_name = scope_node.current.get_scoped_likely_name(name, node)
            if scoped_name:
                return scoped_name
        parent_scope = scope_node.current.parent if scope_node.current else None
        while parent_scope:
            if parent_scope.has_variable(name):
                scoped_name = parent_scope.get_scoped_likely_name(name, node)
                if scoped_name:
                    return scoped_name
            parent_scope = parent_scope.parent
        scoped_name = ''
        child = scope_node.stack[1].get(scope_node.file_path) if len(scope_node.stack) > 1 else None
        if child:
            if child.has_variable(name):
                scoped_name = f"global>{scope_node.file_path}>{name}"
            else:
                scoped_name = f"global>{name}"
        else:
            scoped_name = f"global>{name}"
        return scoped_name
        
    def _process_block_scope_variables(self, definition_map: Optional[DefinitionMapType],
                                       dependency_graph: Optional[DependencyGraphType],
                                       context_tree: Optional[ContextTreeNode],
                                       scope_node: ScopeNode, current: Any,
                                       content: str, start_pos: int, statement: Any):
        node_type = current.type
        if node_type == 'for_statement':
            for_node = current.children[1].children[0]
            if for_node.type == 'identifier':
                variable = for_node
                var_name = variable.text.decode('utf8')
                scoped_name = self._get_scoped_name(var_name, scope_node)
                if definition_map is not None and dependency_graph is not None:
                    self._check_define_node(definition_map, scope_node, variable, content, start_pos, statement, var_name, scoped_name, True)
                    # if scoped_name not in dependency_graph:
                    #     dependency_graph[scoped_name] = set()
                    # dep_set = dependency_graph[scoped_name]
                    # deps: Set[str] = set()
                    # items = current.children[3].children
                    # for child in items:
                    #     self._collect_dependencies_from_expression(definition_map, dependency_graph, None, deps, scope_node, child, content, start_pos, statement)
                    # for dep in deps:
                    #     dep_set.add(dep)
                else:
                    self._create_tree_node(context_tree, scope_node, current, content, start_pos, statement, var_name, scoped_name)
            elif for_node.type == 'variable_list':
                variables = for_node.children
                for variable in variables:
                    if variable.type == 'identifier':
                        var_name = variable.text.decode('utf8')
                        scoped_name = self._get_scoped_name(var_name, scope_node)
                        if definition_map is not None and dependency_graph is not None:
                            self._check_define_node(definition_map, scope_node, variable, content, start_pos, statement, var_name, scoped_name, True)
                            if scoped_name not in dependency_graph:
                                dependency_graph[scoped_name] = set()
                            dep_set = dependency_graph[scoped_name]
                            deps: Set[str] = set()
                            items = current.children[1].children[2].children
                            for child in items:
                                self._collect_dependencies_from_expression(definition_map, dependency_graph, None, deps, scope_node, child, content, start_pos, statement)
                            for dep in deps:
                                dep_set.add(dep)
                        else:
                            self._create_tree_node(context_tree, scope_node, current, content, start_pos, statement, var_name, scoped_name)
    
    def _unary_deal(self, definition_map: Optional[DefinitionMapType],
                   dependency_graph: Optional[DependencyGraphType],
                   keyword_tree: Optional[ContextTreeNode],
                   scope_node: ScopeNode, current: Any,
                   content: str, start_pos: int,
                   statement: Any, parent_type: Any, is_local: bool) -> Optional[ContextTreeNode]:
        name = ''
        scoped_name = ''
        deep = True
        dependency_node = current
        node_type = current.type
        if node_type == 'identifier':
            name = current.text.decode('utf-8')
            if is_local:
                scoped_name = self._get_scoped_name(name, scope_node)
            else:
                scoped_name = f"{self._get_scoped_name(name, scope_node)}-{current.start_byte}"
        elif node_type == 'dot_index_expression':
            name = self._get_function_name(current)
            if name:
                scoped_name = self._get_scoped_name(self._get_function_name(current, True), scope_node)
            deep = False
            dependency_node = current.children[0]
        else:
            name = current.text.decode('utf-8')
            if definition_map is not None and dependency_graph is not None:
                return None
            else:
                return keyword_tree
        if definition_map is not None and dependency_graph is not None:
            # change = self._is_range_change(None, parent_type)
            change = False
            self._check_define_node(definition_map, scope_node, current, content, start_pos, statement, name, scoped_name, change)
            right_deps: Set[str] = set()
            if is_local is False:
                self._collect_dependencies_from_expression(definition_map, dependency_graph,
                                                        keyword_tree, right_deps, scope_node,
                                                        dependency_node, content, start_pos,
                                                        statement, deep)
                if len(right_deps) > 0:
                    if scoped_name not in dependency_graph:
                        dependency_graph[scoped_name] = set()
                    deps = dependency_graph[scoped_name]
                    for dep in right_deps:
                        deps.add(dep)
            return None
        else:
            self._create_tree_node(keyword_tree, scope_node, current, content, start_pos, statement, name, scoped_name)
            return keyword_tree
        
    def _process_identifier_dependencies(self, definition_map: Optional[DefinitionMapType],
                                        dependency_graph: Optional[DependencyGraphType],
                                        keyword_tree: Optional[ContextTreeNode],
                                        scope_node: ScopeNode, current: Any,
                                        content: str, start_pos: int,
                                        statement: Any, parent_type: Any, is_local: bool) -> Optional[ContextTreeNode]:
        return self._unary_deal(definition_map, dependency_graph, keyword_tree, scope_node, current, content, start_pos, statement, parent_type, is_local)
    
    def _process_variable_list_dependencies(self, definition_map: Optional[DefinitionMapType],
                                        dependency_graph: Optional[DependencyGraphType],
                                        keyword_tree: Optional[ContextTreeNode],
                                        scope_node: ScopeNode, current: Any,
                                        content: str, start_pos: int,
                                        statement: Any, parent_type: Any, is_local: bool) -> Optional[ContextTreeNode]:
        variables = current.children
        for variable in variables:
            self._process_identifier_dependencies(definition_map, dependency_graph, keyword_tree, scope_node, variable, content, start_pos, statement, parent_type, is_local)
    
    def _process_assignment_dependencies(self, definition_map: Optional[DefinitionMapType],
                                        dependency_graph: Optional[DependencyGraphType],
                                        keyword_tree: Optional[ContextTreeNode],
                                        scope_node: ScopeNode, current: Any,
                                        content: str, start_pos: int,
                                        statement: Any, is_local: bool) -> Optional[ContextTreeNode]:
        name = ''
        scoped_name = ''
        
        if definition_map is not None and dependency_graph is not None:
            left_vars: List[str] = []
            is_file_local = (is_local and scope_node.current_depth == 0)
            if is_file_local:
                self._enter_new_scope(definition_map, dependency_graph, keyword_tree, scope_node, current, content, start_pos, statement, is_file_local)
            if current.children:
                if len(current.children) == 3 and current.children[0].type == 'variable_list':
                    varaibles = current.children[0].children
                    for variable in varaibles:
                        var_type = variable.type
                        if var_type == 'identifier':
                            name = variable.text.decode('utf8')
                            if is_local:
                                scoped_name = self._get_scoped_name(name, scope_node)
                            else:
                                if scope_node.current_depth == 0:
                                    scoped_name = self._get_scoped_name(name, scope_node)
                                else:
                                    scoped_name = f"{self._get_scoped_name(name, scope_node)}-{current.start_byte}"
                            left_vars.append(scoped_name)
                        elif var_type == 'dot_index_expression':
                            name = self._get_function_name(variable)
                            if name:
                                scoped_name = self._get_scoped_name(self._get_function_name(variable, True), scope_node)
                                left_vars.append(scoped_name)
                        if is_local:
                            self._check_define_node(definition_map, scope_node, current, content, start_pos, statement, name, scoped_name, True)
                        else:
                            self._check_define_node(definition_map, scope_node, variable, content, start_pos, statement, name, scoped_name, True)
            if is_file_local:
                self._exit_scope(scope_node)
            right_deps: Set[str] = set()
            if current.children:
                if len(current.children) == 3 and current.children[2].type == 'expression_list':
                    expressions = current.children[2].children
                    for expr in expressions:
                        self._collect_dependencies_from_expression(definition_map, dependency_graph, keyword_tree, right_deps, scope_node, expr, content, start_pos, statement)
            for left_var in left_vars:
                if len(right_deps) > 0:
                    if left_var not in dependency_graph:
                        dependency_graph[left_var] = set()
                    deps = dependency_graph[left_var]
                    for dep in right_deps:
                        deps.add(dep)
            return None
        else:
            is_file_local = (is_local and scope_node.current_depth == 0)
            if is_file_local:
                self._enter_new_scope(definition_map, dependency_graph, keyword_tree, scope_node, current, content, start_pos, statement, is_file_local)
            if current.children:
                if len(current.children) == 3 and current.children[0].type == 'variable_list':
                    varaibles = current.children[0].children
                    for variable in varaibles:
                        var_type = variable.type
                        if var_type == 'identifier':
                            name = variable.text.decode('utf8')
                            if is_local:
                                scoped_name = self._get_scoped_name(name, scope_node)
                            else:
                                if scope_node.current_depth == 0:
                                    scoped_name = self._get_scoped_name(name, scope_node)
                                else:
                                    scoped_name = f"{self._get_scoped_name(name, scope_node)}-{current.start_byte}"
                        elif var_type == 'dot_index_expression':
                            name = self._get_function_name(variable)
                            if name:
                                scoped_name = self._get_scoped_name(self._get_function_name(variable, True), scope_node)
                        self._create_tree_node(keyword_tree, scope_node, variable, content, start_pos, statement, name, scoped_name)
            if is_file_local:
                self._exit_scope(scope_node)
            return keyword_tree
        
    def _process_member_dependencies(self, definition_map: Optional[DefinitionMapType],
                                     dependency_graph: Optional[DependencyGraphType],
                                     keyword_tree: Optional[ContextTreeNode],
                                     scope_node: ScopeNode, current: Any,
                                     content: str, start_pos: int,
                                     statement: Any, parent_type: Any, is_local: bool) -> Optional[ContextTreeNode]:
        return self._unary_deal(definition_map, dependency_graph, keyword_tree, scope_node, current, content, start_pos, statement, parent_type, is_local)
    
    def _process_call_dependencies(self, definition_map: Optional[DefinitionMapType],
                                  dependency_graph: Optional[DependencyGraphType],
                                  keyword_tree: Optional[ContextTreeNode],
                                  scope_node: ScopeNode, current: Any,
                                  content: str, start_pos: int,
                                  statement: Any) -> Optional[ContextTreeNode]:
        func_name = self._get_function_name(current.children[0])
        if not func_name:
            return None
        func_declare_name = ''
        base = current.children[0]
        if base.type == 'dot_index_expression':
            func_declare_name = self._get_scoped_name(self._get_function_name(base, True), scope_node)
        else:
            func_declare_name = f"{self._get_scoped_name(func_name, scope_node)}-{current.start_byte}"
        if definition_map is not None and dependency_graph is not None:
            self._check_define_node(definition_map, scope_node, current, content, start_pos, statement, func_name, func_declare_name)
            if func_declare_name not in dependency_graph:
                dependency_graph[func_declare_name] = set()
            dep_set = dependency_graph[func_declare_name]
            deps: Set[str] = set()
            for child in current.children:
                if child.type == 'arguments':
                    arguments = child.children
                    for arg in arguments:
                        if arg.type in ['(', ')', ',']:
                            continue
                        self._collect_dependencies_from_expression(definition_map, dependency_graph, keyword_tree, deps, scope_node, arg, content, start_pos, statement)
                    for dep in deps:
                        dep_set.add(dep)
            return None
        else:
            context_tree_node = self._create_tree_node(keyword_tree, scope_node, current, content, start_pos, statement, func_name, func_declare_name)
            return context_tree_node
    
    def _process_function_dependencies(self, definition_map: Optional[DefinitionMapType],
                                      dependency_graph: Optional[DependencyGraphType],
                                      keyword_tree: Optional[ContextTreeNode],
                                      scope_node: ScopeNode, current: Any,
                                      content: str, start_pos: int,
                                      statement: Any) -> Optional[ContextTreeNode]:
        func_name = self._get_scope_name(current, start_pos, 'function')
        scoped_func_name = self._get_scoped_name(func_name, scope_node)
        if definition_map is not None and dependency_graph is not None:
            self._check_define_node(definition_map, scope_node, current, content, start_pos, statement, func_name, scoped_func_name, True)
            if current.children:
                for child in current.children:
                    if child.type == 'parameters':
                        for param in child.children:
                            if param.type == 'identifier':
                                param_name = param.text.decode('utf8')
                                scoped_param_name = self._resolve_scoped_name(scope_node, param_name, param)
                                if scoped_func_name not in dependency_graph:
                                    dependency_graph[scoped_func_name] = set()
                                dependency_graph[scoped_func_name].add(scoped_param_name)
                    elif child.type == 'block':
                        self._enter_new_scope(definition_map, dependency_graph, keyword_tree, scope_node, current, content, start_pos, statement)
                        deps: Set[str] = set()
                        self._collect_dependencies_from_expression(definition_map, dependency_graph, keyword_tree, deps, scope_node, child, content, start_pos, statement)
                        if len(deps) > 0:
                            if scoped_func_name not in dependency_graph:
                                dependency_graph[scoped_func_name] = set()
                            dep_set = dependency_graph[scoped_func_name]
                            for dep in deps:
                                dep_set.add(dep)
                        self._exit_scope(scope_node)
            return None
        else:
            context_tree_node = self._create_tree_node(keyword_tree, scope_node, current, content, start_pos, statement, func_name, scoped_func_name)
            return context_tree_node