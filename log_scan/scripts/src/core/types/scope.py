class Scope:
    def __init__(self, name: str, parent: 'Scope' = None, is_block_scope: bool = False):
        self.name = name
        self.parent = parent
        self.variables = {}  # 变量名 -> 列表，每个元素为 {"scoped_name": str, "change": bool}
        self.full_name = f"{parent.full_name}>{name}" if parent else name
        self.is_block_scope = is_block_scope

    def add_variable(self, name: str, scoped_name: str, change: bool):
        if name not in self.variables:
            self.variables[name] = [{"scoped_name": scoped_name, "change": change}]
        else:
            items = self.variables[name]
            if any(item["scoped_name"] == scoped_name for item in items):
                return
            items.append({"scoped_name": scoped_name, "change": change})

    def has_variable(self, name: str) -> bool:
        return name in self.variables

    def get_scoped_likely_name(self, name: str, node) -> str | None:
        items = self.variables.get(name)
        if not items or len(items) == 0:
            return None

        threshold = node.start_byte # 假设 node 是字典，包含 range 键
        best_name = None
        max_num = -1  # 初始化为 -1，确保 0 也能被选中
        for i in range(len(items) - 1, -1, -1):
            change = items[i]["change"]
            if not change:
                continue
            scoped_name = items[i]["scoped_name"]
            last_dash_index = scoped_name.rfind('-')
            num = 0
            if last_dash_index != -1:
                suffix = scoped_name[last_dash_index + 1:]
                try:
                    num = int(suffix)
                    if num < 0:
                        continue
                except ValueError:
                    continue
            if num < threshold and num > max_num:
                max_num = num
                best_name = scoped_name
                break

        return best_name

    def has_variable_likely(self, base_name: str) -> str | None:
        if self.has_variable(base_name):
            return base_name

        # 2. 构造正则：匹配 base_name-数字
        # Python 中需要转义正则特殊字符
        import re
        escaped_base = re.escape(base_name)
        pattern = f"^{escaped_base}-(\\d+)$"
        regex = re.compile(pattern)

        max_num = -1
        best_match = None

        # 3. 遍历 scope 中所有变量名
        for var_name in self.variables.keys():
            match = regex.match(var_name)
            if match:
                num = int(match.group(1))
                if num > max_num:
                    max_num = num
                    best_match = var_name
                    
        return best_match  # 可能为 None