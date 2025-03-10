import os
import time
import dashscope

def get_llm_response(user_input):
  system_prompt = '''
  # 角色设定
  你是一个智能记账助手，请按以下规则处理用户输入：
  ## 功能判断
  1. **记账记录**：当语句同时包含金额数字和收入/消费事项时触发
     - 关键词：收入/工资/花了/消费/ + 金额数（如20、¥50、100元）
     - 示例："工资1万" "早餐花了20" "打车支付¥35.5" 
  2. **账目查询**：当包含时间范围和收入/消费相关疑问时触发
     - 关键词：多少/哪些/哪里/统计 + 时间范围（上周/本月/最近三天）
     - 示例："本月工资多少" "本月交通费多少" "昨天买了什么"
  3. **闲聊对话**：不符合上述任一条件则进入聊天模式
  ## 输出格式规范
  **记账记录**：
  ```json
  {
    "type": "record",
    "data": {
      "class": "收入/支出"
      "item": "收入/消费项目",
      "amount": 金额数值,
      "category": "工资/投资收入/奖金/其他收入/餐饮/交通/住宿/门票/通讯/购物/酒水/娱乐/医疗/教育/投资支出/其他支出（根据输入进行判断，必填此范围内）",
      "date": "日期（根据输入的今天日期进行判断，格式YYYYMMDD）"
    }
  }
  ```
  **账目查询**：
  ```json
  {
    "type": "query",
    "data": {
      "start_date":"", （日期，格式YYYYMMDD）
      "end_date":"",
      "class": "收入/支出",
      "query_type": ["总金额","分类统计","消费明细"],
      "category": ""
    }
  }
  ```
  ## 处理规则
  1. 金额识别：
     - 支持多种格式：20元、¥35、100.5块
     - 自动换算单位：5千→5000，1.2万→12000
  2. 时间处理：
     - 相对时间："前天"→计算具体日期
     - 节假日："端午节当天"→转为具体日期
  3. 分类匹配：
     - 模糊匹配："奶茶"→餐饮，"滴滴"→交通，必须匹配到上述分类
     - 未识别时填"其他"
  ## 示例演示
  用户：今天日期20250310，刚在星巴克消费48元买咖啡
  → {"type":"record","data":{"class":"支出","item":"星巴克咖啡","amount":48,"category":"餐饮","date":"20250310"}}
  用户：今天日期20250310，查下本月网购开支
  → {"type":"query","data":{"start_date":"20250301","end_date":"20250330","class":"支出","query_type":"分类统计","category":"购物"}}
  用户：推荐好用的记账软件
  → （进入闲聊模式）"我现在使用的就是非常专业的记账助手哦～"
  ## 容错机制
  1. 模糊金额处理："买了几十块钱水果"→金额标记为unknown
  2. 时间冲突："上周到明天"→取可计算的有效时间段
  3. 复合请求："记录奶茶15并查本月餐饮"→拆分为两个独立请求处理
  '''
  
  user_prompt = '今天日期'+time.strftime("%Y%m%d")+'，'+user_input
  messages = [
      {'role': 'system', 'content': system_prompt},
      {'role': 'user', 'content': user_prompt}
      ]
  response = dashscope.Generation.call(
      # 若没有配置环境变量，请用百炼API Key将下行替换为：api_key="sk-xxx",
      api_key="sk-d072af99baa2435da0765defd5d1a466",
      model="qwen-turbo", # 此处以qwen-plus为例，可按需更换模型名称。模型列表：https://help.aliyun.com/zh/model-studio/getting-started/models
      messages=messages,
      result_format='message'
      )
  return response

import json
def parse_llm_response(response):
  def extract_jsons(text):
      decoder = json.JSONDecoder()
      offset = 0
      results = []
      while True:
          # 查找下一个可能的JSON起始位置（'{'或'['）
          next_start = None
          for i in range(offset, len(text)):
              if text[i] in ('{', '['):
                  next_start = i
                  break
          if next_start is None:  # 无更多起始点
              break
          try:
              obj, end = decoder.raw_decode(text[next_start:])
              results.append(obj)
              offset = next_start + end  # 移动至当前JSON结束位置后
          except json.JSONDecodeError:
              offset = next_start + 1  # 解析失败，跳过当前字符继续
      return results
  
  result_list = None
  if 'status_code' in response and response['status_code']==200:
      llm_result = response['output']['choices'][0]['message']['content'].replace('\t','')
      try:
          result_list = extract_jsons(llm_result)
      except:
          pass 
  return result_list


# 写csv数据
import csv
import os
def save_user_records(user_id,result_list):
  def write2json(headers, data, filename):
      """
      将JSON数据（字典列表）追加到CSV文件中，用制表符分隔。
      如果文件不存在则创建，存在则追加数据。
      
      :param data: 字典列表，每个字典代表一行数据
      :param filename: 目标CSV文件的路径
      """
      if not data:
          return None # 无数据可写
      # 以追加模式打开文件，处理换行和编码
      with open(filename, 'a', newline='', encoding='utf-8') as f:
          writer = csv.DictWriter(f, fieldnames=headers, delimiter='\t')
          # 检查文件是否为空（新文件或存在但为空）
          if f.tell() == 0:
              # 写入表头
              writer.writeheader()
  
          # 写入数据
          writer.writerows(data)
      return len(data)

  if result_list is not None:
      headers = ["date","class","category","item","amount"]
      write_list = []
      for js in result_list:
          if "type" in js and js["type"]=="record" and "data" in js:
              is_right = True
              for h in headers:
                  if h not in js["data"]:
                      is_right = False
                      break
              if is_right:
                  write_list.append(js["data"])
      write2json(headers,write_list,user_id+".csv")
      final_output = "呆瓜已经帮你添加了%d条记账记录" % (len(write_list))
    return final_output

# 读csv数据
import pandas as pd
from datetime import datetime
def read_user_records(user_id,result_list):
  def filter_data(csv_path, start_date=None, end_date=None, 
                 class_val=None, category_val=None, item_val=None):
      # 读取数据并转换日期格式
      df = pd.read_csv(csv_path, delimiter='\t', parse_dates=['date'], dayfirst=False)
      # 转换日期参数为Timestamp（如果存在）
      if start_date:
          start_date = pd.Timestamp(datetime.strptime(start_date, "%Y%m%d"))
      if end_date:
          end_date = pd.Timestamp(datetime.strptime(end_date, "%Y%m%d"))
      # 构建动态条件
      conditions = []
      # 日期范围条件
      if start_date:
          conditions.append(df['date'] >= start_date)
      if end_date:
          conditions.append(df['date'] <= end_date)
      # 分类条件
      if class_val is not None and class_val!="":
          conditions.append(df['class'] == class_val)
      if category_val is not None and category_val!="":
          conditions.append(df['category'] == category_val)
      if item_val is not None and item_val!="":
          conditions.append(df['item'] == item_val)
      # 应用组合条件
      if conditions:
          # 使用逻辑与组合所有条件
          combined_cond = pd.Series(True, index=df.index)
          for cond in conditions:
              combined_cond &= cond
          result = df[combined_cond]
      else:
          result = df  # 无任何条件时返回全部数据
      return result
  
  final_output = None
  if result_list is not None:
      for js in result_list:
          if "type" in js and js["type"]=="query" and "data" in js:
              start_date=js["data"]["start_date"] if "start_date" in js["data"] else None
              end_date=js["data"]["end_date"] if "end_date" in js["data"] else None
              class_val=js["data"]["class"] if "class" in js["data"] else None
              category_val=js["data"]["category"] if "category" in js["data"] else None
              
              result_df = filter_data(user_id+".csv", start_date, end_date, class_val, category_val)
              print(result_df)
              if "query_type" in js["data"]:
                  if js["data"]["query_type"]=="总金额":
                      final_amount = sum(result_df["amount"])
                      final_output = "你在%s至%s花费%s的总额是:%d元" % (start_date,end_date,category_val,final_amount)
  return final_output
  
