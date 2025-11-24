import streamlit as st
import akshare as ak
import pandas as pd
import plotly.express as px
import datetime
import warnings

# --- 0. 屏蔽烦人的警告信息 ---
warnings.filterwarnings("ignore")
st.set_option('deprecation.showPyplotGlobalUse', False)

# --- 1. 页面配置 ---
st.set_page_config(page_title="A股复盘(终极版)", layout="wide", page_icon="🐲")

# 注入CSS：隐藏默认菜单，优化表格显示
st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
        .block-container {padding-top: 1.5rem;}
        div[data-testid="stExpander"] div[role="button"] p {font-size: 16px; font-weight: bold;}
    </style>
""", unsafe_allow_html=True)

st.title("🐲 A股涨停题材深度复盘")
st.caption("数据源：东方财富 | 核心：题材归因 + 连板梯队 + 资金容量")

# --- 2. 核心数据处理 (超强容错) ---

@st.cache_data(ttl=300)
def get_zt_data_final(date_str):
    """
    终极版数据获取：暴力适配所有可能的列名
    """
    try:
        # 获取原始数据
        df = ak.stock_zt_pool_em(date=date_str)
        
        if df is None or df.empty:
            return None, None

        # --- A. 智能匹配“题材”列 (核心逻辑) ---
        # 东方财富接口的列名经常变，这里做一个优先级的字典匹配
        # 优先级：涨停原因类别 > 所属行业 > 行业 > 概念
        theme_col = None
        possible_cols = ['涨停原因类别', '所属行业', '行业', '概念']
        
        for col in possible_cols:
            if col in df.columns:
                theme_col = col
                break
        
        if theme_col:
            df['题材'] = df[theme_col]
        else:
            df['题材'] = "未知题材" # 实在找不到时的保底

        df['题材'] = df['题材'].fillna('其他')

        # --- B. 智能匹配“连板数”列 ---
        if '连板数' not in df.columns:
             if '涨停统计' in df.columns:
                 # 处理 "2/2" 这种格式
                 df['连板数'] = df['涨停统计'].apply(lambda x: int(str(x).split('/')[0]) if '/' in str(x) else 1)
             else:
                 df['连板数'] = 1 

        # --- C. 资金与价格清洗 ---
        def to_float_100m(x):
            try:
                return float(x) / 100000000
            except:
                return 0.0

        # 优先用成交额
        if '成交额' in df.columns:
            df['成交额(亿)'] = df['成交额'].apply(to_float_100m)
        else:
            df['成交额(亿)'] = 0.0

        if '封板资金' in df.columns:
            df['封板资金(亿)'] = df['封板资金'].apply(to_float_100m)
        else:
             df['封板资金(亿)'] = 0.0

        # --- D. 生成统计表 ---
        theme_stats = df.groupby('题材').agg(
            涨停家数=('名称', 'count'),
            总成交额=('成交额(亿)', 'sum'),
            最高板=('连板数', 'max')
        ).reset_index()
        
        # 计算占比
        theme_stats['占比'] = (theme_stats['涨停家数'] / len(df) * 100).round(1)
        theme_stats['总成交额(亿)'] = theme_stats['总成交额(亿)'].round(2)
        
        # 排序：先按家数，再按金额
        theme_stats = theme_stats.sort_values(by=['涨停家数', '总成交额(亿)'], ascending=[False, False])
        
        return df, theme_stats

    except Exception as e:
        print(f"Error: {e}")
        return None, None

# --- 3. 侧边栏 ---
with st.sidebar:
    st.header("🎮 控制台")
    if st.button("🔄 强制刷新数据"):
        st.cache_data.clear()
        st.rerun()
        
    # 智能设置默认日期：如果是周末，自动跳到上周五
    today = datetime.date.today()
    if today.weekday() == 5: # 周六
         today -= datetime.timedelta(days=1)
    elif today.weekday() == 6: # 周日
         today -= datetime.timedelta(days=2)
    # 如果是周一早上9点前，也跳到上周五
    if today.weekday() == 0 and datetime.datetime.now().hour < 15:
         today -= datetime.timedelta(days=3)
    
    select_date = st.date_input("复盘日期", today)
    date_str = select_date.strftime("%Y%m%d")
    st.caption(f"当前查询: {date_str}")

# --- 4. 主页面 ---

df_stocks, df_themes = get_zt_data_final(date_str)

if df_stocks is None:
    st.warning(f"⚠️ {date_str} 暂无涨停数据。")
    st.info("💡 提示：如果是交易日，数据通常在 15:30 后更新。请尝试更改日期。")
else:
    # === 1. 市场概览 ===
    st.subheader("1. 市场情绪概览")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔥 涨停家数", f"{len(df_stocks)}")
    c2.metric("💰 涨停成交", f"{df_stocks['成交额(亿)'].sum():.1f} 亿")
    c3.metric("🚀 空间高度", f"{df_stocks['连板数'].max()} 板")
    # 计算平均连板
    avg_board = df_stocks['连板数'].mean()
    c4.metric("📈 平均连板", f"{avg_board:.2f}")

    # === 2. 可视化图表 ===
    st.subheader("2. 题材热度与资金")
    if not df_themes.empty:
        top_15 = df_themes.head(15)
        
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.markdown("**🔥 题材热度 (涨停家数)**")
            fig1 = px.bar(top_15, x='题材', y='涨停家数', text='涨停家数', 
                          color='涨停家数', color_continuous_scale='Reds')
            # 隐藏一些不必要的轴标题，让图更清爽
            fig1.update_layout(xaxis_title=None, yaxis_title=None, coloraxis_showscale=False)
            st.plotly_chart(fig1, use_container_width=True)
            
        with col_chart2:
            st.markdown("**💰 题材容量 (总成交额/亿)**")
            fig2 = px.bar(top_15, x='题材', y='总成交额(亿)', text='总成交额(亿)', 
                          color='总成交额(亿)', color_continuous_scale='Viridis')
            fig2.update_layout(xaxis_title=None, yaxis_title=None, coloraxis_showscale=False)
            st.plotly_chart(fig2, use_container_width=True)

    # === 3. 题材梯队详情 ===
    st.subheader("3. 题材梯队深度解析")
    st.markdown("👇 **点击下方卡片，查看各题材龙头与梯队**")

    for idx, row in df_themes.iterrows():
        t_name = row['题材']
        t_count = row['涨停家数']
        t_money = row['总成交额(亿)']
        t_high = row['最高板']
        
        # 筛选数据
        subset = df_stocks[df_stocks['题材'] == t_name].copy()
        # 排序：连板数降序 -> 封单降序
        subset = subset.sort_values(by=['连板数', '封板资金(亿)'], ascending=[False, False])
        
        # 标题栏
        label = f"【{t_name}】 🔥{t_count}家 | 🚀最高{t_high}板 | 💰{t_money}亿"
        
        with st.expander(label):
            # 准备列
            show_cols = ['代码', '名称', '最新价', '涨跌幅', '连板数', '成交额(亿)', '封板资金(亿)', '换手率']
            final_cols = [c for c in show_cols if c in subset.columns]
            
            # 样式：高亮最高板
            def highlight_leader(s):
                if s['连板数'] == t_high and t_high >= 2: # 2板以上才高亮
                    return ['background-color: #ffebee'] * len(s)
                return [''] * len(s)

            st.dataframe(
                subset[final_cols].style
                .apply(highlight_leader, axis=1)
                .format("{:.2f}", subset=['成交额(亿)', '封板资金(亿)']),
                use_container_width=True,
                hide_index=True
            )
