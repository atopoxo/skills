import os
from typing import List, Dict, Set, Tuple, Any
from core.ai_model.base.ai_types import ContextOption, ContextTreeNode, ContextItem
from core.context.base.context_base import ContextBase
from core.context.lua.lua_context import LuaContext, ScopeNode
from core.types.scope import Scope
from core.function.segment_tree import SegmentTree
from core.function.deque import Deque

class ContextMgr(ContextBase):
    def __init__(self, extension_name: str):
        super().__init__()
        self.extension_name = extension_name
        self.filters = ['js', 'ts', 'py', 'lua', 'c', 'cc', 'h', 'hpp', 'cpp']
        self.folder_black_list = ['node_modules', 'build', '.git', '.vscode']
        self.lua_context = LuaContext()
        self.context_name_max_length = 120
        self.include_filters = ['scripts/ai/argumentStrings.ls', 'LuaEnvInit/EditorExportedStrings']
        self.max_depth = 1
    
    def init(self):
        super().init()
    
    def get_context_name_max_length(self) -> int:
        return self.context_name_max_length
    
    def get_relevant_context(self, start_pos: int, select_content: str, file_content: str, file_path: str, encoding: str) -> List[ContextOption]:
        result = []
        if len(select_content) > 0:
            item_map = self.get_related_context(start_pos, select_content, file_content, file_path, encoding)
            for key, items in item_map.items():
                for item in items:
                    item['paths'] = [key]
                    option = self.context_item_to_option(item)
                    result.append(option)
        return result
    
    def get_context(self, context: List[ContextOption], encoding: str, replace_byte: bool) -> str:
        result = ""
        unique_context_ids = set()
        parts = {
            'function': [],
            'code': [],
            'file': []
        }
        for i, item in enumerate(context):
            try:
                self.process_context(parts, unique_context_ids, item, encoding, replace_byte)
            except Exception as ex:
                print(f"处理index={i}的上下文时发生异常: {ex}")

        if len(parts['function']) > 0 or len(parts['code']) > 0 or len(parts['file']) > 0:
            result += "以下是上下文引用:\n"
        if len(parts['function']) > 0:
            result += "\n函数引用:\n"
            result += "\n".join(parts['function']) + "\n"
        if len(parts['code']) > 0:
            result += "\n代码片段引用:\n"
            result += "\n".join(parts['code']) + "\n"
        if len(parts['file']) > 0:
            result += "\n文件引用:\n"
            result += "\n".join(parts['file']) + "\n"
        return result
    
    def process_context(self, parts: Dict, unique_context_ids: Set[str], option: ContextOption, encoding: str, replace_byte: bool):
        ref = option['context_item']
        if ref:
            content = ref['content'].decode(encoding)
            if option['type'] in ['file', 'folder']:
                if option['id'] not in unique_context_ids:
                    unique_context_ids.add(option['id'])
                    parts[option['type']].append(f"{ref['paths'][0]}:\\n{content}\\n")
            else:
                if option['id'] not in unique_context_ids:
                    unique_context_ids.add(option['id'])
                    parts[option['type']].append(content)
            if replace_byte:
                ref['content'] = content
                ref['name'] = ref['name'].decode(encoding, errors='ignore')
                option['name'] = option['name'].decode(encoding, errors='ignore')
        if 'children' in option:
            for child in option['children']:
                self.process_context(parts, unique_context_ids, child, encoding, replace_byte)
    
    def get_related_context(self, start_pos: int, select_content: str, file_content: str, file_path: str, encoding: str) -> Dict[str, List[ContextItem]]:
        result = {}
        identifiers = self._get_identifiers(0, file_path, file_content, encoding)
        if not identifiers:
            return result
        keyword_tree = ContextTreeNode(
            value={
                'type': 'global',
                'name': 'global',
                'range': {
                    'start': 0,
                    'end': len(identifiers['content'])
                }
            },
            children=[]
        )
        root_scope = Scope('global', None)
        root_scopes = {'global': root_scope}
        scope_node = ScopeNode(
            stack=[root_scopes],
            current=root_scope,
            current_depth=0,
            file_path=file_path
        )
        self.lua_context.build_tree(keyword_tree, scope_node, identifiers['ast'], identifiers['content'], 0)
        range_tree = SegmentTree(0, len(identifiers['content']))
        range_tree.update(start_pos, start_pos + len(select_content), 1)
        items = []
        self._get_identifiers_by_range(items, keyword_tree, start_pos, start_pos + len(select_content))
        queue = Deque()
        for item in items:
            queue.push_back(item['name'])
        visited = set()
        selected = {
            'file_path': file_path,
            'range': {
                'start': start_pos,
                'end': start_pos + len(select_content)
            }
        }
        
        self.find_related_context(queue, file_path, identifiers['ast'], identifiers['content'], result, visited, 0, range_tree, selected, encoding)
        return result
    
    def find_related_context(self, queue: Deque, file_path: str, ast: Any, content: str,
                          result: Dict[str, List[ContextItem]], visited: Set[str],
                          depth: int, range_tree: SegmentTree = None,
                          selected: Dict = None, encoding: str = "utf8"):
        dependency_graph = {}
        definition_map = {}
        root_scope = Scope('global', None)
        root_scopes = {'global': root_scope}
        scope_node = ScopeNode(
            stack=[root_scopes],
            current=root_scope,
            current_depth=0,
            file_path=file_path
        )
        self.lua_context.build_dependency_graph(definition_map, dependency_graph, scope_node, ast, content, 0)
        visited_identifiers = set()
        miss_queue = Deque()
        miss_set = set()
        if file_path not in result:
            result[file_path] = []
        while not queue.is_empty():
            current = queue.pop_front()
            defined_node = definition_map.get(current)
            if defined_node:
                key = f"{file_path}:{current}"
                if key in visited:
                    continue
                visited.add(key)
                if defined_node['name'] in visited_identifiers:
                    continue
                visited_identifiers.add(defined_node['name'])
                if not defined_node.get('range'):
                    continue
                if range_tree:
                    range_tree.update(defined_node['range']['start'], defined_node['range']['end'], 1)
                dependencies = dependency_graph.get(defined_node['name'], set())
                for dep in dependencies:
                    if dep not in visited_identifiers:
                        queue.push_back(dep)
            else:
                if current in miss_set:
                    continue
                miss_set.add(current)
                if self.lua_context.is_valid_global_string(current):
                    miss_queue.push_back(current)
        while not miss_queue.is_empty():
            item = miss_queue.pop_front()
            queue.push_back(item)
        if selected and selected['file_path'] == file_path and range_tree:
            range_tree.update(selected['range']['start'], selected['range']['end'], 0)
        if range_tree:
            ranges = range_tree.get_range(0, len(content), 1)
            pos_list = self._get_pos_list(content)
            self.create_context_items_by_range(result[file_path], ranges, content, pos_list)
        if not queue.is_empty():
            includes = self._extract_includes(content, os.path.splitext(file_path)[1], encoding)
            for i in range(len(includes) - 1, -1, -1):
                include = includes[i]
                include_path = self._resolve_include_path(file_path, include)
                if include_path and depth < self.max_depth:
                    filter_flag = False
                    for filter in self.include_filters:
                        if filter in include_path:
                            filter_flag = True
                            break
                    if filter_flag:
                        continue
                    include_identifiers = self._get_identifiers(0, include_path, None, encoding)
                    if not include_identifiers:
                        continue
                    current_range_tree = SegmentTree(0, len(include_identifiers['content']))
                    self.find_related_context(queue, include_path, include_identifiers['ast'], include_identifiers['content'], result, visited, depth + 1, current_range_tree, selected, encoding)
    
    def create_context_items_by_range(self, result: List[ContextItem], source: List[Tuple[int, int]],
                                  content: str, pos_list: List[int]):
        for start, end in source:
            text = content[start:end]
            name = text[:self.context_name_max_length]
            current = ContextItem(
                type='code',
                name=name,
                content=text,
                range={
                    'start': start,
                    'end': end,
                    'start_line': self._get_line_count(pos_list, start),
                    'end_line': self._get_line_count(pos_list, end)
                }
            )
            result.append(current)