#举例说明：
cpp_code:
```cpp
98: BOOL KHairCustomDyeingSettings::LoadCustomDyeingTable(const char cszFileName[])
99: {
100:     BOOL      bResult   = false;
101:     BOOL      bRetCode  = false;
102:     ITabFile* piTabFile = NULL;
103:     int       nHeight   = 0;
104: 
105:     KGLOG_PROCESS_ERROR(cszFileName);
106: 
107:     piTabFile = g_OpenTabFile(cszFileName);
108:     KG_PROCESS_SUCCESS(piTabFile == NULL);
109: 
110:     piTabFile->SetErrorLog(false);
111:     nHeight = piTabFile->GetHeight();
112:     KGLOG_PROCESS_ERROR(nHeight >= 1);
113: 
114:     for (int nLine = 2; nLine <= nHeight; nLine++)
115:     {
116:         KHAIR_CUSTOM_DYEING_INFO Info;
117: 
118:         bRetCode = LoadCustomDyeingTableLine(piTabFile, nLine, Info);
119:         KGLOG_PROCESS_ERROR(bRetCode);
120: 
121:         KGLOG_PROCESS_ERROR(Info.nType >= 0 && Info.nType < hcdtTotal);
122:         KGLOG_PROCESS_ERROR(m_CustomDyeingInfo[Info.nType].nType == 0);
123: 
124:         m_CustomDyeingInfo[Info.nType] = Info;
125:     }
126: 
127: Exit1:
128:     bResult = true;
129: Exit0:
130:     if (!bResult && cszFileName)
131:     {
132:         KGLogPrintf(KGLOG_ERR, "Load '%s' failed.", cszFileName);
133:     }
134:     KG_COM_RELEASE(piTabFile);
135:     return bResult;
136: }

298: BOOL KHairCustomDyeingSettings::LoadCustomDyeingTableLine(ITabFile* piTabFile, int nLine, KHAIR_CUSTOM_DYEING_INFO& rInfo)
299: {
300:     BOOL bResult = false;
301: 
302:     KGLOG_PROCESS_ERROR(piTabFile);
303: 
304:     piTabFile->GetInteger(nLine, "Type", 0, &rInfo.nType);
305:     KGMLOG_PROCESS_ERROR(rInfo.nType >= 0 && rInfo.nType < hcdtTotal, nLine, rInfo.nType);
306: 
307:     piTabFile->GetInteger(nLine, "ValueMin", 0, &rInfo.nValueMin);
308:     KGMLOG_PROCESS_ERROR(rInfo.nValueMin >= MIN_HAIR_CUSTOM_DYEING_PARAM_VALUE, nLine, rInfo.nValueMin);
309: 
310:     piTabFile->GetInteger(nLine, "ValueMax", 0, &rInfo.nValueMax);
311:     KGMLOG_PROCESS_ERROR(rInfo.nValueMax >= rInfo.nValueMin && rInfo.nValueMax <= MAX_HAIR_CUSTOM_DYEING_PARAM_VALUE, nLine, rInfo.nValueMax);
312: 
313:     bResult = true;
314: Exit0:
315:     return bResult;
316: }
```
返回如下结果：
<<<-<<<代码片段1
[
    {
        "error_line": 112,
        "error_msg": "KGLOG_PROCESS_ERROR(nHeight >= 1)",
        "tab_attribute": "GetHeight",
    },
    {
        "error_line": 121,
        "error_msg": "KGLOG_PROCESS_ERROR(Info.nType >= 0 && Info.nType < hcdtTotal)",
        "tab_attribute": "Type",
    },
    {
        "error_line": 122,
        "error_msg": "KGLOG_PROCESS_ERROR(m_CustomDyeingInfo[Info.nType].nType == 0)",
        "tab_attribute": "Type",
    },
    {
        "error_line": 305,
        "error_msg": "KGMLOG_PROCESS_ERROR(rInfo.nType >= 0 && rInfo.nType < hcdtTotal, nLine, rInfo.nType)",
        "tab_attribute": "Type",
    },
    {
        "error_line": 308,
        "error_msg": "KGMLOG_PROCESS_ERROR(rInfo.nValueMin >= MIN_HAIR_CUSTOM_DYEING_PARAM_VALUE, nLine, rInfo.nValueMin)",
        "tab_attribute": "ValueMin",
    },
    {
        "error_line": 311,
        "error_msg": "KGMLOG_PROCESS_ERROR(rInfo.nValueMax >= rInfo.nValueMin && rInfo.nValueMax <= MAX_HAIR_CUSTOM_DYEING_PARAM_VALUE, nLine, rInfo.nValueMax)",
        "tab_attribute": "ValueMax",
    }
]
>>>->>>