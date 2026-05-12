---
name: cpp_coding_rule
description: 剑网三 C/C++ 代码规范。当编写、审查或修改 C/C++ 代码时使用此技能。涵盖命名约定、格式化、函数设计、内存管理、错误处理等规范。
type: skill
---

# 剑网三 C/C++ 代码规范

本规范合并自《剑网三代码规范自检手册》及项目补充规范，适用于所有 C/C++ 代码的编写、审查和修改。

---

## 一、头文件规范

### 1.1 头文件保护

头文件**必须**使用 `#ifndef/#define/#endif` 方式防止重复包含，宏名**必须**遵循 `__H_*_H__` 格式，**严禁**使用 `#pragma once` 或任何其他形式。

宏名格式：`__H_<文件名>_H__`，文件名中的 `.` 替换为 `_`，全部大写。

```cpp
// Skill.h
#ifndef __H_SKILL_H__
#define __H_SKILL_H__
// ...
#endif  // __H_SKILL_H__

// SkillManager.h
#ifndef __H_SKILLMANAGER_H__
#define __H_SKILLMANAGER_H__
// ...
#endif  // __H_SKILLMANAGER_H__
```

`#endif` 后必须以注释标注对应的宏名。**严禁**使用 `#pragma once`。

### 1.2 文件头注释

每个头文件必须包含标准的文件头注释块：

```cpp
///////////////////////////////////////////////////////////////
// Copyright(c) Kingsoft
//
// FileName : SkillManager.h
// Creator  : ShaoYi
// Date     : 2026-05-12 15:10:00
// Comment  : Manage the global skill data and save it of all levels.
//
///////////////////////////////////////////////////////////////
```

### 1.3 include 顺序

include 的顺序遵循从外到内的原则，相同类型的头文件放在一起：

```cpp
// 1. C 标准库
#include <sys/types.h>
#include <unistd.h>

// 2. C++ 标准库
#include <string>
#include <vector>

// 3. 第三方库 .h
#include "base/basictypes.h"
#include "base/commandlineflags.h"

// 4. 本项目 .h（使用从项目根目录的完整路径）
#include "foo/server/bar.h"
```

- 使用 `#include` 时用从项目根目录开始的完整相对路径
- 不要包含未使用的头文件
- `.cpp` 文件中第一个 `#include` 必须是`stdafx.h`，其次是对应 `.h` 文件

---

## 二、格式化规范

### 2.1 大括号

`if`、`for`、`while`、`do` 等语句**必须**使用大括号，即使只有一行：

```cpp
// 正确
if (!nResult) {
    break;
}

// 错误
if (!nResult)
    break;
```

### 2.2 指针和引用

`*` 和 `&` 紧贴类型名，不贴变量名：

```cpp
// 正确
Skill* pSkill = NULL;
Skill* pSkill = NULL;

// 错误
Skill *pSkill = NULL;
Skill * pSkill = NULL;
```

### 2.3 空格规范

**二元运算符两侧加空格：**

```cpp
// = += >= <= + * % && || << ^ 等运算符两侧加空格
nResult = nA + nB;
if (nA >= nB && nC < nD) { ... }
for (int i = 0; i < nMaxCount; i++) { ... }
```

**一元运算符后不加空格：**

```cpp
// ! ~ ++ -- &（取地址）
if (!nResult) { ... }
nIndex++;
Skill* pSkill = &skill;
```

**成员访问运算符两侧不加空格：**

```cpp
// [] . -> ::
itMentor->first;
m_MentorPushMap[nIndex];
pApply->dwApplyPlayerID;
```

**函数调用格式：** 函数名后紧跟 `(`，参数间 `,` 后加空格：

```cpp
Function(a, b);
```

### 2.4 列对齐

在函数定义中，变量声明和定义需要**列对齐**：类型部分上下对齐，变量名部分上下对齐，`=` 部分上下对齐：

```cpp
void OnApplyMentor(BYTE* pbyData, size_t uDataLen, int nConnIndex)
{
    int                                     nMaxCount   = 0;
    BOOL                                    bRetCode    = false;
    Role*                                   pRole       = NULL;
    IKG_Buffer*                             piBuffer    = NULL;
    R2S_PUSH_MENTOR_OR_APPRENTICE_LIST*     pPushInfo   = NULL;
    // ...
}
```

对齐规则：
- 类型列左对齐（按最长类型名对齐）
- 变量名列对齐（按最长变量名对齐）
- `=` 列对齐
- 初始化值列对齐
- **所有局部变量都必须参与列对齐**，包括没有 `=` 初始化的变量（如 `std::string`、迭代器等），它们的类型列和变量名列也必须与其他变量对齐
- **`=` 必须上下对齐**：所有带 `=` 的变量定义，其 `=` 列必须严格对齐，不得出现某一行的 `=` 偏移

**类成员变量声明中同样适用列对齐规则**，与函数定义中变量对齐规则一致：

```cpp
class SkillManager {
private:
    static int          m_nSkillCount;
    static SkillManager* m_pInstance;
    uint64_t            m_uCurrentUID;
    std::string         m_strDataDir;
    std::map<int, int>  m_SomeMap;
};
```

### 2.5 垂直间距

**变量声明后空一行：** 函数开头的变量声明/定义块结束后，必须有一行空行，然后再开始函数体的实现逻辑：

```cpp
BOOL SomeFunction(int nParam)
{
    BOOL    bResult     = false;
    int     nCount      = 0;
    Role*   pRole       = NULL;

    LOG_PROCESS_ERROR(nParam > 0);

    // ... 业务逻辑 ...
Exit0:
    return bResult;
}
```

**禁止连续多余空行：** 函数体内不允许出现连续两个或以上的空行。函数定义之间保留一个空行即可，不要插入多余空行。

```cpp
// 正确：函数间一个空行
void FuncA()
{
    // ...
}

void FuncB()
{
    // ...
}

// 错误：多余空行
void FuncA()
{
    // ...
}


void FuncB()
{
    // ...
}
```

---

## 三、命名规范

### 3.1 类名

类名使用 PascalCase：

```cpp
class ItemNull { ... };
class SkillManager { ... };
```

### 3.2 析构函数

**所有类的析构函数必须声明为 `virtual`**，无论该类是否被继承：

```cpp
class ItemNull {
public:
    virtual ~ItemNull(void);
};

class SkillManager {
public:
    virtual ~SkillManager(void);
};
```

### 3.3 结构体名

结构体以 `S` 开头，全部大写，使用下划线分隔：

```cpp
struct S2R_REGISTER_MENTOR_OR_APPRENTICE_PUSH { ... };
```

### 3.4 函数名

函数名使用 PascalCase，动词开头：

```cpp
int GetPointer();
int SetSize(float fWidth, float fHight);
BOOL PushApprenticeInfo(int nForceID, int nMaxCount);
```

### 3.5 变量名——匈牙利命名法

变量名由**类型前缀** + **PascalCase 描述**组成：

| 前缀 | 类型 | 示例 |
|------|------|------|
| `n` | int / DWORD | `nResult`, `nMaxCount` |
| `b` | BOOL | `bResult`, `bRetCode` |
| `p` | 指针 | `pSkill`, `pPushList` |
| `f` | float | `fWidth`, `fHight` |
| `sz` | 以 '\0' 结尾的字符串 | `szComment` |
| `pcsz` | const char*（常量字符串指针） | `pcszPos`, `pcszName` |
| `by` | BYTE | `byData` |
| `dw` | DWORD | `dwRoleID` |
| `u` | unsigned | `uDataLen` |
| `it` | 迭代器 (iterator) | `itMentor`, `itFileData` |

> **迭代器命名规则：** 迭代器必须以 `it` 为前缀，后接描述性名称（PascalCase），禁止使用裸名 `it`。

> **`const char*` 命名规则：** `const char*` 类型变量**必须**以 `pcsz` 为前缀，后接描述性名称（PascalCase），禁止使用 `psz`、`sz` 等其他前缀。例如 `const char* pcszFileName = NULL;`。

**作用域前缀：**

| 前缀 | 含义 |
|------|------|
| `m_` | 类成员变量 (member)，**包括静态成员变量** |
| `g_` | 全局变量 (global) |
| `s_` | 非成员静态变量 (static，文件作用域) |

```cpp
class SkillManager {
    int m_nSkillCount;            // 成员变量
    static int m_nInstanceCount;  // 静态成员变量，同样用 m_
};

SkillManager* g_pSkillManager;   // 全局变量
```

### 3.6 其他命名规则

- **所有函数名不得以 `_` 开头**
- 循环计数器使用 `i`、`j`、`k`，或带类型前缀的 `nIndex`、`nI`
- 常量放在声明开头，使用 `const` 或 `static` 修饰
- 避免无意义的缩写：`nCurrentValue` 而非 `nCrtValue`
- 避免无意义的变量名：`int a, b, a1` 不允许

---

## 四、函数设计规范

### 4.1 单一返回点

**函数只能有一个返回点**。中间不能有 `return`，必须通过 `goto Exit0`（或 `goto Exit1`）跳转到函数末尾再 `return`。构造函数除外。

**`return` 只会存在于 `Exit0` 标签后**，即使 `Exit0` 被注释也是如此。函数体内除 `Exit0` 标签之后的 `return` 外，不得存在任何其他 `return` 语句。

```cpp
BOOL DoRegister(const char* pcszComment, BOOL bMentor)
{
    BOOL bResult = false;

    // ... 业务逻辑 ...

    bResult = true;
Exit0:
    return bResult;
}
```

**错误处理使用 `LOG_PROCESS_ERROR` / `PROCESS_ERROR` 宏**，这些宏内部使用 `goto Exit0`：

```cpp
BOOL PushMentorInfo(int nMaxCount, MentorInfo* pPushList, int* pnRetCount)
{
    BOOL               bResult         = false;
    int                nRealCount      = 0;
    int                nMentorMapCount = 0;
    PUSH_MAP::iterator itMentor;

    LOG_PROCESS_ERROR(pPushList);
    LOG_PROCESS_ERROR(pnRetCount);

    *pnRetCount = 0;
    // ...

    bResult = true;
Exit0:
    return bResult;
}
```

**返回值模式：**
- `bResult` 初始化为 `false`
- 函数执行成功后，在 `goto Exit0` 之前设置为 `true`
- `Exit0:` 标签后只做 `return bResult`

**空指针检查必须使用项目宏，禁止手写 if-goto：**

`LOG_PROCESS_ERROR(condition)` —— condition 为 false 时跳转到 Exit0，用于错误退出路径：

```cpp
// 错误
if (pszInput == NULL)
{
    goto Exit0;
}

// 正确
LOG_PROCESS_ERROR(pszInput != NULL);
```

`LOG_PROCESS_SUCCESS(condition)` —— condition 为 true 时跳转到 Exit1，用于提前成功退出路径：

```cpp
// 错误
if (pszInput == NULL)
{
    goto Exit1;
}

// 正确
LOG_PROCESS_SUCCESS(pszInput == NULL);
```

**死标签必须注释掉：** 如果函数体内没有任何 `goto` 语句或 `LOG_PROCESS_ERROR`/`PROCESS_ERROR`/`LOG_PROCESS_SUCCESS` 宏需要跳转到 `Exit0:` 或 `Exit1:`，则这些标签必须被注释掉（改为 `//Exit0:` 和 `//Exit1:`），否则会产生编译警告：

```cpp
// 有 goto/LOG_PROCESS_ERROR 的函数 —— 标签保持活跃
BOOL ComplexFunction()
{
    BOOL bResult = false;

    LOG_PROCESS_ERROR(someCondition);
    // ...
    bResult = true;
Exit1:
Exit0:
    return bResult;
}

**非 void 函数**（返回 BOOL 等）即使无 goto 也必须在函数末尾保留 `//Exit1:` 和 `//Exit0:` 注释标签。

**void 函数中如果不需要使用 Exit1 和 Exit0 标签，则直接删掉这两个标签**。反之，如果任何其中一个标签被使用（通过 `goto` 或 `LOG_PROCESS_ERROR`/`PROCESS_ERROR`/`LOG_PROCESS_SUCCESS`），另外一个标签也必须存在，只是如果没被用到，需要注释掉（`//Exit1:` 或 `//Exit0:`）。

```cpp
// void 函数无 goto/宏跳转 —— 标签直接删除
void SimpleVoidFunction()
{
    // ... 简单逻辑 ...
}

// void 函数有一个标签被使用 —— 另一个也保留并注释
void ComplexVoidFunction()
{
    // ...
    if (error)
    {
        goto Exit0;
    }
    // ...
//Exit1:
Exit0:
    return;
}
```

**标签顺序固定为 Exit1 在 Exit0 之前：** 无论标签是活跃状态还是被注释掉，`Exit1:` 必须始终在 `Exit0:` 之前。这是固定的物理顺序，不受标签是否被注释的影响。

### 4.2 IN/OUT 参数宏

- 函数参数如果会被修改并返回给调用者，使用 `OUT` 宏标记
- 函数参数如果仅作为输入，使用 `IN` 宏标记
- **OUT 参数放在 IN 参数前面**
- IN/OUT 宏是项目已定义的宏（`#define IN`、`#define OUT`），不需要查找其实现

```cpp
// 正确: OUT 参数在前
int PushInfo(int* OUT pnRetCount, MentorInfo* OUT pPushInfo, DWORD IN dwRoleID, BOOL IN bMentorOrApprentice, int IN nMaxCount);

// 错误: IN/OUT 在函数定义中：
int PushInfo(DWORD IN dwRoleID, BOOL IN bMentorOrApprentice, int* OUT pnRetCount, MentorInfo* OUT pPushInfo, int IN nMaxCount)
{
    // ...
}
```

### 4.3 非静态函数优先

**类的实现中尽量用非静态函数代替静态函数**。只有在方法确实不依赖实例状态时才使用 `static`。

```cpp
class SkillManager {
public:
    int GetSkillCount();        // 优先使用非静态
    // static int GetVersion(); // 除非必要，不用静态
};
```

### 4.4 switch/case 格式化

`switch` 中的 `case` 必须正确缩进，每个 `case` 需要 `break`（除非有意的 fall-through 且注释说明）。

---

## 五、变量声明和初始化

### 5.1 声明位置

**变量的声明和定义必须放在函数定义的开头**（C89 风格），且**变量定义尽可能放在变量声明之前**，否则可能被代码中的 `goto` 等宏跳过导致编译错误。

例外：代码块的局部变量，且该代码块中不存在 `goto` 等可能跳过声明和定义的宏。

```cpp
BOOL SomeFunction(int nParam)
{
    // 1. 先放带初始化的变量定义
    BOOL    bResult     = false;
    int     nCount      = 0;
    Role*   pRole       = NULL;

    // 2. 再放不带初始化的变量声明
    PUSH_MAP::iterator itMentor;

    LOG_PROCESS_ERROR(nParam > 0);

    // ...
Exit0:
    return bResult;
}
```

### 5.2 变量初始化

**所有变量在声明时如果可以,必须初始化**，使用适当的初始化值：

| 类型 | 初始化值 | 示例 |
|------|---------|------|
| int / DWORD | `0` | `int nResult = 0;` |
| float | `0.0f` | `float fScale = 0.0f;` |
| BOOL | `false` | `BOOL bResult = false;` |
| 指针 | `NULL` / `nullptr` | `Skill* pSkill = NULL;` |
| std::string | `""` | `std::string strName = "";` |
| char | `'\0'` | `char cFlag = '\0';` |

---

## 六、内存管理

### 6.1 分配后检查

使用 `new` 分配内存后必须检查指针有效性：

```cpp
Skill* pSkill = new Skill;
PROCESS_ERROR(pSkill);
```

### 6.2 释放后置空

使用 `delete` 后必须将指针置为 `NULL`：

```cpp
if (pSkill) {
    delete pSkill;
    pSkill = NULL;
}
```

### 6.3 配对使用

- `malloc`/`free` 必须配对
- `new`/`delete` 必须配对
- `new[]`/`delete[]` 必须配对

---

## 七、初始化规范

### 7.1 结构体和类初始化

使用 `{}` 或 `=` 进行初始化，或实现 `Init()` 方法。不要在构造后直接逐成员赋值。

```cpp
// 正确：使用构造函数或 Init()
class Item {
public:
    Item() : m_nCount(0), m_pData(NULL) {}
    int Init();
};

// 或使用 {} 初始化
SOME_STRUCT stData = {0};
```

---

## 八、常见陷阱与禁止事项

### 8.1 比较运算

- **不能链式比较：** `if (a < b < c)` 是错误的，应写为 `if ((a < b) && (b < c))`
- **浮点数不能直接判等：** 应使用范围比较 `if ((fVal >= target - EPSILON) && (fVal <= target + EPSILON))`
- 浮点字面量加类型后缀：`float fPI = 3.14f;`，比较时也要：`if (fPI == 3.14f)`
- **整型与整型比较**，不可与浮点比较后赋值给整型

### 8.2 运算符优先级

复杂表达式中使用括号明确优先级，不要依赖默认优先级。

### 8.3 宏陷阱

- 宏参数必须用括号保护：`#define ADD(a, b) ((a) + (b))`
- **不能将有副作用的表达式传入宏：** `SQUARE(i++)` 会导致未定义行为

### 8.4 数组与字符串

- **不越界访问：** `szArray[10]` 在大小为 10 的数组中是非法的
- **不返回局部数组的指针：** 函数返回的 `char*` 不能指向栈上的数组
- **字符串常量不可修改：** `const char* p = "Hello"; p[0] = 'x';` 是错误的
- **使用安全函数：** 用 `strncpy` 替代 `strcpy`，用 `strncmp` 替代 `strcmp`
- **`strncpy` 后主动补 `'\0'`：** `strncpy(str1, str2, sizeof(str1)); str1[sizeof(str1) - 1] = '\0';`
- 字符串长度取 sizeof 时注意：Unicode 字符串的字节长度 ≠ 字符数

### 8.5 循环

- 复杂条件判断放在循环外部，不要在循环体内重复判断
- 确保循环计数器正确递增，避免死循环
- 嵌套循环使用不同的计数器变量

### 8.6 其他

- **除零检查：** 除法/取模前检查除数不为零
- **整数溢出：** 注意运算结果是否会溢出
- **printf 格式说明符：** 必须匹配参数类型，打印字符串用 `%s` 而非 `%d`
- **避免 `*p++` 等易混淆写法：** 拆分为多条语句
- **`switch` 中每个 `case` 必须 `break`**（除非有明确的 fall-through 注释）
- **`goto` 不能跳过变量声明：** 这也是第 5.1 节要求变量放在函数开头的原因

---

## 九、可移植性

- 代码需要同时支持 Windows 和 Linux 平台
- 使用 `assert()` 进行调试检查（包含对应头文件 `<assert.h>`）
- 使用与平台无关的标准库接口

---

## 十、代码审查检查清单

在提交代码前自查以下项目：

1. [ ] 头文件保护宏必须为 `__H_*_H__` 格式，`#endif` 后有注释标注，禁止 `#pragma once`
2. [ ] include 路径正确、顺序合理、无冗余
3. [ ] 所有 if/for/while 都有大括号
4. [ ] 指针/引用符号紧贴类型
5. [ ] 变量声明/定义列对齐，且在函数开头
6. [ ] `=` 列上下严格对齐
7. [ ] 命名符合匈牙利命名法规范（含 `pcsz` 前缀）
8. [ ] 函数名不以 `_` 开头
9. [ ] 函数只有一个返回点（构造函数除外）
10. [ ] 空指针检查使用 LOG_PROCESS_ERROR/LOG_PROCESS_SUCCESS 而非手写 if-goto
11. [ ] 无 goto 的非 void 函数中 Exit0:/Exit1: 已注释；void 函数无 goto 则标签已删除，有一个标签被使用则另一标签保留并注释
12. [ ] `return` 仅存在于 Exit0 标签之后
13. [ ] 错误处理使用 PROCESS_ERROR 宏
14. [ ] OUT修饰的传入参数在前，IN修饰的传入参数在后
15. [ ] 所有变量声明时已初始化
16. [ ] 内存分配后检查，释放后置 NULL
17. [ ] 使用 strncpy/strncmp 而非 strcpy/strcmp
18. [ ] strncpy 后主动补 '\0'
19. [ ] 复杂表达式使用括号明确优先级
20. [ ] 变量声明块与函数逻辑间有空行
21. [ ] 无连续多余空行，函数间仅一个空行
22. [ ] 无数组越界、无除零、无返回局部指针等问题
	23. [ ] 所有类的析构函数声明为 virtual
