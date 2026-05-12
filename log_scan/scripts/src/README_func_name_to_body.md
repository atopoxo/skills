# func_name_to_body.py 使用说明

## 功能
从C/C++源代码中提取函数名和函数体，输出为JSON格式。

## 支持的函数名格式
1. 嵌套类: `KCoinShop::KCoinShopVoucherSettings::LoadVoucherSettings`
2. 普通类: `KCoinShopVoucherSettings_vk::LoadVoucherSettings`
3. 全局函数: `DynamicLoadVoucherSettings`

## 使用方法

### 基本用法（使用默认路径）
```bash
python func_name_to_body.py
```

### 指定源代码路径
```bash
python func_name_to_body.py "i:\your\source\path"
```

### 指定输出文件
```bash
python func_name_to_body.py -o output.json
```

### 指定文件编码（默认为gbk）
```bash
python func_name_to_body.py -e utf-8
```

### 显示详细信息
```bash
python func_name_to_body.py -v
```

## 输出格式
程序会生成一个JSON文件，格式如下：
```json
{
  "KAcceptQuest::KAcceptQuest": "{\n    m_pQuestInfo    = NULL;\n    m_bFailed       = false;\n    m_nLimitTime    = 0;\n    m_nRoundCount   = 0;\n}",
  "KAcceptQuest::Init": "{\n    BOOL    bResult = false;\n    // ... 函数体内容\n}",
  // ... 更多函数
}
```

## 示例
运行以下命令提取默认路径下的所有函数：
```bash
cd i:\SVN\trunk\Sword3\Source\QATools\LogScan\src
python func_name_to_body.py -v -o all_functions.json
```

## 注意事项
1. 程序使用基于大括号匹配的简化解析方法，对于复杂的模板和宏定义可能无法完美处理
2. 默认编码为gbk，如果文件编码不同，请使用`-e`参数指定
3. 输出文件默认保存在当前目录，文件名格式为`{目录名}_functions.json`

## 测试程序
还提供了一个测试程序：
```bash
python test_func_extractor.py
```

这个程序会检查输出文件的格式是否符合要求。