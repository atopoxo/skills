import json
import os
import re
from typing import Dict, List, Set, Optional, Any, Callable
import tree_sitter_lua
from tree_sitter import Language, Parser
from core.ai_model.base.ai_types import ContextOption, ContextItem, ContextTreeNode
from core.function.trie import Trie
from core.function.base_function import get_file_content

class Range:
    def __init__(self, start: int, end: int):
        self.start = start
        self.end = end

ContextNode = Dict[str, Any] # { ast: any, tree: ContextTreeNode, content: str }

IdentifierType = str # Literal type: 'function' | 'variable' | 'closure' | 'constant'
ParserFormat = Callable[[str, List[IdentifierType], int], ContextNode]

class ContextBase:
    def __init__(self):
        self.language_parsers: Dict[str, ParserFormat] = {
            'lua': self.__parse_lua,
            'lh': self.__parse_lua,
            'ls': self.__parse_lua,
        }
        self.lua_property_filters: Set[str] = set()
        self.language_cache: Dict[str, Any] = {} # Map<string, any>
        self._init_lua_property_filters()

    def _init_lua_property_filters(self):
        filters = ['type', 'range', 'loc', 'base', 'identifier']
        self.lua_property_filters.update(filters)

    def init(self):
        self.parser = Parser()
        # self.language_ts = self._load_language_wasm('typescript')
        self.language_lua = Language(tree_sitter_lua.language())
        self.parser.language = self.language_lua
        self.current_language = "lua"

    def context_item_to_option(self, item: ContextItem) -> ContextOption:
        name = ''
        if len(item['paths']) > 0:
            name = item['paths'][0]
        start_line = item['range']['start_line'] if item['range'] and item['range']['start_line'] else 0
        end_line = item['range']['end_line'] if item['range'] and item['range']['end_line'] else 0
        return {
            'type': 'code',
            'id': f'{name}:{start_line}~{end_line}',
            'name': item['name'],
            'describe': '',
            'context_item': item
        }

    def _load_language_wasm(self, lang: str) -> Any:
        if lang in self.language_cache:
            return self.language_cache[lang]
        
        wasm_filename = f"tree-sitter-{lang}"
        wasm_path = os.path.join(wasm_filename, f"{wasm_filename}.wasm")
        try:
            language = Language(wasm_path, lang)
            self.language_cache[lang] = language
            return language
        except Exception as e:
            print(f"加载 WASM 失败: {e}")
            return None

    def _get_identifiers(self, start_pos: int, file_path: str, content: Optional[str] = None, encoding: str = "utf8") -> Optional[ContextNode]:
        try:
            ext = os.path.splitext(file_path)[1].lower()[1:]
            parser_func = self.language_parsers.get(ext)
            if not parser_func:
                return None
            content_bytes = content
            if content is None:
                content = get_file_content(file_path, encoding=encoding)
                content = content.replace("\r\n", "\n")
                content_bytes = bytes(content, encoding)
            
            types: List[IdentifierType] = []
            result = parser_func(content_bytes, types, start_pos, encoding)
            return result
        except Exception as ex:
            print(f"Error processing file: {file_path}", ex)
            return None

    def _get_identifiers_by_range(self, result: List[ContextItem], current: ContextTreeNode, start_pos: int, end_pos: int):
        if not current['value']:
            return
        context = current['value']
        if 'range' not in context:
            return
        if context['name'] != 'global' and start_pos <= context['range']['start'] and context['range']['end'] <= end_pos:
            result.append(context)
            return
        for child in current['children']:
            if not child['value']:
                continue
            child_node = child['value']
            if 'range' not in child_node:
                continue
            if child_node['range']['end'] <= start_pos:
                continue
            if child_node['range']['start'] >= end_pos:
                break
            self._get_identifiers_by_range(result, child, start_pos, end_pos)

    def _traverse_tree(self, result: Dict[str, ContextTreeNode], current: ContextTreeNode):
        value = current.value
        if value:
            result[value['name']] = current
        for child in current.children:
            self._traverse_tree(result, child)

    def _tree_to_trie(self, result: Trie[ContextTreeNode], current: ContextTreeNode):
        value = current.value
        if value:
            result.insert(value['name'], current)
        for child in current.children:
            self._tree_to_trie(result, child)

    def _extract_includes(self, content: str, ext: str, encoding: str) -> List[str]:
        includes: List[str] = []
        regex: Optional[re.Pattern] = None

        if ext in ['.c', '.cpp', '.h', '.hpp']:
            regex = re.compile(rb'#include\s+["<]([^">]+)[">]')
        elif ext == '.lua':
            regex = re.compile(rb'(?:require|Include)\s*\(?["\']([^"\']+)["\']\)?')
        elif ext == '.py':
            regex = re.compile(rb'import\s+([^\s#]+)|from\s+([^\s#]+)\s+import')
        elif ext in ['.js', '.ts']:
            regex = re.compile(rb"import\s+.*['\"]([^'\"]+)['\"]|require\s*\(['\"]([^'\"]+)['\"]\)")
        else:
            return []

        matches = regex.finditer(content)
        for match in matches:
            for i in range(1, len(match.groups()) + 1):
                if match.group(i):
                    includes.append(match.group(i).decode(encoding))
                    break
        return includes

    def _resolve_include_path(self, current_path: str, include: str) -> Optional[str]:
        current_dir = os.path.dirname(current_path)
        base_path = self._find_base_path(current_dir, include)
        if base_path:
            full_path = os.path.join(base_path, include)
            full_path = full_path.replace('\\', '/')
            if os.path.exists(full_path):
                return full_path
            return self._try_extensions(full_path)
        return self._try_other_resolutions(current_dir, include)

    def _find_base_path(self, path1: str, path2: str) -> Optional[str]:
        parts1 = os.path.abspath(path1).replace('\\', '/').split('/')
        parts2 = path2.replace('\\', '/').split('/')

        common_parts: List[str] = []
        base_parts: List[str] = []

        i, j = 0, 0
        while i < len(parts1) and j < len(parts2):
            if parts1[i] == parts2[j]:
                common_parts.append(parts1[i])
                j += 1
            else:
                if len(common_parts) > 0:
                    break
                base_parts.append(parts1[i])
            i += 1

        return '/'.join(base_parts) if len(common_parts) > 0 else None

    def _try_other_resolutions(self, current_dir: str, include: str) -> Optional[str]:
        relative_path = os.path.abspath(os.path.join(current_dir, include))
        if os.path.exists(relative_path):
            return relative_path
        with_ext = self._try_extensions(relative_path)
        if with_ext:
            return with_ext
        workspace_root = self._get_workspace_root(current_dir)
        if workspace_root:
            root_path = os.path.abspath(os.path.join(workspace_root, include))
            if os.path.exists(root_path):
                return root_path
            lib_path = os.path.abspath(os.path.join(workspace_root, 'lib', include))
            if os.path.exists(lib_path):
                return lib_path
        node_modules_path = self._find_in_node_modules(current_dir, include)
        if node_modules_path:
            return node_modules_path
        return None

    def _try_extensions(self, full_path: str) -> Optional[str]:
        extensions = ['.lua', '.js', '.ts', '.py', '.c', '.cpp', '.h', '.hpp', '']
        if os.path.exists(full_path):
            return full_path
        for ext in extensions:
            with_ext = full_path + ext
            if os.path.exists(with_ext):
                return with_ext
        if os.path.exists(full_path) and os.path.isdir(full_path):
            for ext in extensions:
                index_file = os.path.join(full_path, f"index{ext}")
                if os.path.exists(index_file):
                    return index_file
        return None

    def _get_workspace_root(self, current_path: str) -> Optional[str]:
        # Simulate getting the workspace root from VSCode API
        # In a real scenario, this would interact with the environment
        # For now, we'll just return the first folder in a simulated list
        workspace_folders = [{'uri': {'fsPath': '/home/user/my_project'}}] # Placeholder
        if not workspace_folders:
            return None
        for folder in workspace_folders:
            folder_path = folder['uri']['fsPath']
            if current_path.startswith(folder_path):
                return folder_path
        return workspace_folders[0]['uri']['fsPath']

    def _try_find_lua_file(self, module_path: str) -> Optional[str]:
        if os.path.exists(module_path):
            return module_path
        with_lua_ext = f"{module_path}.lua"
        if os.path.exists(with_lua_ext):
            return with_lua_ext
        if os.path.isdir(module_path):
            init_path = os.path.join(module_path, 'init.lua')
            if os.path.exists(init_path):
                return init_path
        return None

    def _find_in_node_modules(self, start_dir: str, module_name: str) -> Optional[str]:
        current_dir = start_dir
        while current_dir != os.path.dirname(current_dir): # Reached root
            node_modules_path = os.path.join(current_dir, 'node_modules', module_name)
            package_path = os.path.join(node_modules_path, 'package.json')
            if os.path.exists(package_path):
                try:
                    with open(package_path, 'r', encoding='utf-8') as f:
                        pkg = json.load(f)
                    if pkg.get('main'):
                        main_path = os.path.join(node_modules_path, pkg['main'])
                        if os.path.exists(main_path):
                            return main_path
                except (json.JSONDecodeError, FileNotFoundError) as e:
                    print(f"Error reading package.json: {package_path}", e)
            module_files = [
                f"{module_name}.js",
                f"{module_name}.ts",
                f"{module_name}/index.js",
                f"{module_name}/index.ts"
            ]
            for file in module_files:
                file_path = os.path.join(node_modules_path, file)
                if os.path.exists(file_path):
                    return file_path
            current_dir = os.path.dirname(current_dir)
        return None

    def __parse_lua(self, content: str, types: List[IdentifierType], start_pos: int, encoding: str) -> ContextNode:
        if self.current_language != "lua":
            self.parser.set_language(self.language_lua)
        tree = self.parser.parse(content)
        ast = tree.root_node
        root: ContextTreeNode = {
            "value": {
                "type": "global",
                "name": "global",
                "range": {
                    "start": start_pos,
                    "end": start_pos + len(content)
                }
            },
            "children": []
        }
        if len(types) > 0:
            self._traverse_lua(ast, root['value']['name'], types, root, content, start_pos)
        return {"ast": ast, "tree": root, "content": content}

    def _traverse_lua(self, node: Any, parent_name: str, types: List[IdentifierType], parent: Optional[ContextTreeNode], content: str, start_pos: int):
        current: Optional[ContextTreeNode] = None
        if isinstance(node, dict) and node.type == 'function_declaration':
            current = self._lua_function_declaration(node, parent_name, types, content, start_pos)

        current_name = parent_name
        if current:
            if parent:
                parent.children.append(current)
            current_name = current.value['name'] if current.value else current_name
        else:
            current = parent

        if isinstance(node, dict):
            for key, value in node.items():
                if key in self.lua_property_filters:
                    continue
                if isinstance(value, (list, dict)):
                    if isinstance(value, list):
                        for child in value:
                            if child:
                                self._traverse_lua(child, current_name, types, current, content, start_pos)
                    else:
                        self._traverse_lua(value, current_name, types, current, content, start_pos)

    def _lua_function_declaration(self, node: Any, parent_name: str, types: List[IdentifierType], content: str, start_pos: int) -> Optional[ContextTreeNode]:
        current: Optional[ContextTreeNode] = None
        for type_val in types:
            if type_val == 'function':
                item = self._create_context_item_for_lua(
                    node, node['type'], parent_name, False, self._get_lua_function_name(node.get('identifier')), content, start_pos
                )
                current = ContextTreeNode(item)
                break
        return current

    def _get_lua_function_name(self, identifier: Any) -> str:
        if not identifier:
            return 'anonymous'
        if identifier['type'] == 'identifier':
            return identifier['name']
        elif identifier['type'] == 'dot_index_expression':
            return f"{self._get_lua_function_name(identifier.get('base'))}.{self._get_lua_function_name(identifier.get('identifier'))}"
        else:
            return ''

    def _get_dot_function_name(self, prefix_node: Any, name_node: Any) -> Dict[str, Any]:
        # Simulate logic for accessing member functions in tree-sitter
        # This is highly dependent on the specific tree-sitter query results
        prefix_text = getattr(prefix_node, 'text', '')
        name_text = getattr(name_node, 'text', '')
        return {
            "text": f"{prefix_text}.{name_text}",
            "startIndex": getattr(prefix_node, 'startIndex', 0),
            "endIndex": getattr(name_node, 'endIndex', 0)
        }

    def _find_table_variable_name(self, table_node: Any) -> Optional[str]:
        parent = getattr(table_node, 'parent', None)
        while parent:
            if getattr(parent, 'type', '') == 'assignment_statement':
                left_child = getattr(parent, 'childForFieldName', lambda x: None)('left')
                if left_child and getattr(left_child, 'type', '') == 'variable_list':
                    first_var = getattr(left_child, 'child', lambda x: None)(0)
                    if first_var and getattr(first_var, 'type', '') == 'identifier':
                        return getattr(first_var, 'text', '')
            parent = getattr(parent, 'parent', None)
        return None

    def _is_inside_class(self, node: Any) -> bool:
        parent = getattr(node, 'parent', None)
        while parent:
            if getattr(parent, 'type', '') == 'class_definition':
                return True
            parent = getattr(parent, 'parent', None)
        return False

    def _find_function_name_in_declarator(self, declarator: Any) -> Optional[Any]:
        decl_type = getattr(declarator, 'type', '')
        if decl_type == 'identifier':
            return declarator
        if decl_type == 'function_declarator':
            declarator_node = getattr(declarator, 'childForFieldName', lambda x: None)('declarator')
            if declarator_node:
                return self._find_function_name_in_declarator(declarator_node)
        elif decl_type == 'parenthesized_declarator':
            return self._find_function_name_in_declarator(declarator.child(1))
        elif decl_type == 'qualified_identifier':
            name_node = getattr(declarator, 'childForFieldName', lambda x: None)('name')
            if name_node:
                return name_node
        for i in range(getattr(declarator, 'childCount', 0)):
            child = declarator.child(i)
            if child:
                result = self._find_function_name_in_declarator(child)
                if result:
                    return result
        return None

    def _context_item_to_options(self, result: List[ContextOption], file_path: str, content: str, pos_list: List[int], current: ContextTreeNode):
        value = current.value
        if value and value['type'] != 'global':
            value['paths'] = [file_path]
            if 'range' in value:
                value['range']['startLine'] = self._get_line_count(pos_list, value['range']['start'])
                value['range']['endLine'] = self._get_line_count(pos_list, value['range']['end'])
                text = content[value['range']['start']:value['range']['end']]
                value['content'] = text
            item = self._context_item_to_option(value)
            result.append(item)

        for child in current.children:
            self._context_item_to_options(result, file_path, content, pos_list, child)

    def _context_item_to_option(self, item: ContextItem) -> ContextOption:
        path_list = item.get('paths')
        name = path_list[0] if path_list else ''
        
        option_id = f"{name}:{item['range']['startLine']}~{item['range']['endLine']}" if 'range' in item else name

        context_option: ContextOption = {
            "type": 'code',
            "id": option_id,
            "name": item['name'],
            "describe": f"{item['type']}: {item['name']}",
            "context_item": item
        }
        return context_option

    def _get_pos_list(self, content: str) -> List[int]:
        items = content.split(b'\n')
        result = []
        now_pos = 0
        for item in items:
            now_pos += len(item) + 1
            result.append(now_pos)
        return result

    def _get_line_count(self, pos_list: List[int], pos: int) -> int:
        left, right = 0, len(pos_list) - 1
        mid = 0
        while left < right:
            mid = (left + right) // 2
            if pos_list[mid] <= pos:
                left = mid + 1
            else:
                right = mid
        return left