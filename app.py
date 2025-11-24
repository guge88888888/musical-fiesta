import streamlit as st
import akshare as ak
import pandas as pd
import plotly.express as px
import datetime
import warnings

# --- 0. 基础配置 (删除了报错的那一行) ---
warnings.filterwarnings("ignore")
st.set_page_config(page_title="A股复盘(最终修复版)", layout="wide", page_icon="📈")

# 注入CSS：美化界面
st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        .block-container {padding-top: 1.5rem;}
        div[data-testid="stMetricValue"] {font-size: 20px;}
    </style>
""", unsafe_allow_html=True)

st.title("📈 A股涨停题材深度复盘")
st.caption("数据源：东方财富 | 状态：已修复 Streamlit 配置错误")

# --- 1. 核心数据获取 (暴力适配) ---

@st.cache_data(ttl=300)
def get_zt_data_robust(date_str):
    try:
        # 获取原始数据
        df = ak.stock_zt_pool_em(date=date_str)
        
        if df is None or df.empty:
            return None, None

        # --- A. 寻找题材列 ---
        # 依次尝试可能的列名
        theme_col = None
        for col in ['涨停原因类别', '所属行业', '行业', '概念']:
            if col in df.columns:
                theme_col = col
                break
        
        if theme_col:
            df['题材'] = df[theme_col]
        else:
            df['题材'] = "其他题材" # 保底

        df['题材'] = df['题材'].fillna('其他')

        # --- B. 寻找连板数列 ---
        if '连板数' not in df.columns:
             if '涨停统计' in df.columns:
                 # 处理 "2/2" 格式
                 df['连板数'] = df['涨停统计'].apply(lambda x: int(str(x).split('/')[0]) if '/' in str(x) else 1)
             else:
                 df['连板数'] = 1 

        # --- C. 资金清洗 ---
        def clean_money(x):
            try:
                # 如果是字符串且包含万/亿，这里简单处理，通常接口返回的是数值
                return float(x) / 100000000
            except:
                return 0.0

        if '成交额' in df.columns:
            df['成交额(亿)'] = df['成交额'].apply(clean_money)
        else:
            df['成交额(亿)'] = 0.0
            
        if '封板资金' in df.columns:
            df['封板资金(亿)'] = df['封板资金'].apply(clean_money)
        else:
            df['封板资金(亿)'] = 0.0

        # --- D. 统计聚合 ---
        # 按题材分组
        theme_stats = df.groupby('题材').agg(
            涨停家数=('名称', 'count'),
            总成交额=('成交额(亿)', 'sum'),
            最高板=('连板数', 'max')
        ).reset_index()
        
        # 排序
        theme_stats = theme_stats.sort_values(by=['涨停家数', '总成交额(亿)'], ascending=[False, False])
        
        return df, theme_stats

    except Exception as e:
        st.error(f"数据获取出错: {e}")
        return None, None

# --- 2. 侧边栏控制 ---
with st.sidebar:
    st.header("🎮 控制台")
    if st.button("🔄 强制刷新"):
        st.cache_data.clear()
        st.rerun()
        
    # 智能日期：避开周末和周一早盘
    today = datetime.date.today()
    if today.weekday() == 5: today -= datetime.timedelta(days=1)
    elif today.weekday() == 6: today -= datetime.timedelta(days=2)
    # 周一盘中前也看上周五
    if today.weekday() == 0 and datetime.datetime.now().hour < 15:
         today -= datetime.timedelta(days=3)
         
    select_date = st.date_input("复盘日期", today)
    date_str = select_date.strftime("%Y%m%d")

# --- 3. 主界面显示 ---

df_stocks, df_themes = get_zt_data_robust(date_str)

if df_stocks is None:
    st.warning(f"⚠️ {date_str} 暂无数据。")
    st.info("提示：请点击侧边栏的日期，尽量选择上一个完整的交易日（例如上周五）。")
else:
    # 1. 概览
    c1, c2, c3 = st.columns(3)
    c1.metric("🔥 涨停总数", f"{len(df_stocks)}")
    c2.metric("💰 总成交额", f"{df_stocks['成交额(亿)'].sum():.1f} 亿")
    c3.metric("🚀 最高连板", f"{df_stocks['连板数'].max()} 板")

    # 2. 图表
    st.subheader("📊 题材热度排行")
    if not df_themes.empty:
        # 只取前15名，防止图表太长
        top_data = df_themes.head(15)
        
        fig = px.bar(
            top_data, 
            x='题材', 
            y='涨停家数', 
            color='总成交额(亿)', # 颜色深浅代表资金大小
            text='涨停家数',
            color_continuous_scale='Reds',
            title=f"题材涨停家数 & 资金容量 ({date_str})"
        )
        st.plotly_chart(fig, use_container_width=True)
    
    # 3. 详细列表
    st.subheader("📋 题材梯队详情")
    st.markdown("**点击下方列表查看个股明细 👇**")
    
    for _, row in df_themes.iterrows():
        t_name = row['题材']
        t_count = row['涨停家数']
        t_high = row['最高板']
        t_money = row['总成交额(亿)']
        
        # 筛选个股
        subset = df_stocks[df_stocks['题材'] == t_name].copy()
        subset = subset.sort_values(by=['连板数', '封板资金(亿)'], ascending=[False, False])
        
        # 标题
        label = f"【{t_name}】 {t_count}家 | 🚀{t_high}板 | 💰{t_money}亿"
        
        with st.expander(label):
            # 展示列
            cols = ['代码', '名称', '最新价', '涨跌幅', '连板数', '成交额(亿)', '封板资金(亿)']
            final_cols = [c for c in cols if c in subset.columns]
            
            # 高亮样式
            def highlight_leader(s):
                if s['连板数'] == t_high and t_high > 1:
                    return ['background-color: #ffebee'] * len(s)
                return [''] * len(s)

            st.dataframe(
                subset[final_cols].style.apply(highlight_leader, axis=1).format("{:.2f}", subset=['成交额(亿)', '封板资金(亿)']),
                use_container_width=True,
                hide_index=True
            )
