import streamlit as st
import akshare as ak
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import datetime

# --- 1. 页面基础设置 ---
st.set_page_config(page_title="A股深度复盘(题材版)", layout="wide", page_icon="🔥")

# CSS 优化：调整字体和间距，使其更像专业的复盘软件
st.markdown("""
    <style>
        .block-container {padding-top: 2rem; padding-bottom: 2rem;}
        div[data-testid="stMetricValue"] {font-size: 18px;}
        .stExpander {border: 1px solid #f0f2f6; border-radius: 5px;}
    </style>
""", unsafe_allow_html=True)

st.title("🔥 A股涨停题材深度复盘")
st.caption("逻辑核心：事件驱动归因 -> 题材容量分析 -> 连板梯队排序")

# --- 2. 核心数据获取与处理 ---

@st.cache_data(ttl=600)
def get_zt_data_processed(date_str):
    """
    获取涨停数据并进行深加工：清洗、类型转换、分组统计
    """
    try:
        with st.spinner(f'正在深度挖掘 {date_str} 的涨停数据...'):
            df = ak.stock_zt_pool_em(date=date_str)
            if df is None or df.empty:
                return pd.DataFrame(), pd.DataFrame()
            
            # 1. 字段映射与清洗 (以防接口字段变动)
            # 确保关键列存在
            needed_cols = {
                '代码': '代码', '名称': '名称', '最新价': '最新价', 
                '涨跌幅': '涨跌幅', '成交额': '成交额', '流通市值': '流通市值',
                '换手率': '换手率', '连板数': '连板数', '封板资金': '封板资金',
                '涨停原因类别': '题材' # 核心字段
            }
            
            # 过滤掉不存在的列
            available_cols = {k: v for k, v in needed_cols.items() if k in df.columns}
            df = df[list(available_cols.keys())].rename(columns=available_cols)
            
            # 2. 数据类型强转 (清洗脏数据)
            def clean_money(x):
                # 统一转换为“亿元”
                if isinstance(x, (int, float)):
                    return float(x) / 100000000
                return 0.0

            if '成交额' in df.columns:
                df['成交额(亿)'] = df['成交额'].apply(clean_money)
            
            if '封板资金' in df.columns:
                df['封板资金(亿)'] = df['封板资金'].apply(clean_money)

            # 连板数转整数
            df['连板数'] = pd.to_numeric(df['连板数'], errors='coerce').fillna(1).astype(int)

            # 3. 题材聚合统计
            if '题材' in df.columns:
                # 填充空题材
                df['题材'] = df['题材'].fillna("其他")
                
                # 聚合计算
                theme_stats = df.groupby('题材').agg(
                    涨停家数=('名称', 'count'),
                    总成交额=('成交额(亿)', 'sum'),
                    平均连板=('连板数', 'mean'),
                    高标高度=('连板数', 'max')
                ).reset_index()
                
                # 计算占比
                total_zt = len(df)
                theme_stats['家数占比(%)'] = (theme_stats['涨停家数'] / total_zt * 100).round(1)
                theme_stats['总成交额(亿)'] = theme_stats['总成交额(亿)'].round(2)
                
                # 排序：默认按家数降序，家数一样按金额降序
                theme_stats = theme_stats.sort_values(by=['涨停家数', '总成交额(亿)'], ascending=[False, False])
                
                return df, theme_stats
            else:
                return df, pd.DataFrame()

    except Exception as e:
        st.error(f"数据处理发生错误: {e}")
        return pd.DataFrame(), pd.DataFrame()

# --- 3. 侧边栏 ---
with st.sidebar:
    st.header("🎮 复盘控制台")
    today = datetime.date.today()
    # 自动调整到最近的交易日（简单逻辑）
    if today.weekday() == 5: today -= datetime.timedelta(days=1)
    elif today.weekday() == 6: today -= datetime.timedelta(days=2)
    
    select_date = st.date_input("复盘日期", today)
    date_str = select_date.strftime("%Y%m%d")
    
    if st.button("🔄 刷新最新数据"):
        st.cache_data.clear()
        st.rerun()
        
    st.info("💡 **说明**：\n数据来源：东方财富\n逻辑：基于【涨停原因类别】进行题材归因，并统计资金容量。")

# --- 4. 主界面逻辑 ---

df_stocks, df_themes = get_zt_data_processed(date_str)

if df_stocks.empty:
    st.warning(f"⚠️ {date_str} 暂无数据。如果是交易日，请在收盘后（15:30后）查看完整数据。")
else:
    # === 第一部分：全局概览 ===
    st.subheader("1. 市场情绪概览")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔥 今日涨停总数", f"{len(df_stocks)} 家")
    c2.metric("💰 涨停股总成交", f"{df_stocks['成交额(亿)'].sum():.1f} 亿")
    c3.metric("🚀 最高连板", f"{df_stocks['连板数'].max()} 板")
    # 计算首板占比
    first_board = len(df_stocks[df_stocks['连板数']==1])
    c4.metric("🌱 首板占比", f"{first_board/len(df_stocks)*100:.0f}%")

    # === 第二部分：图表可视化 ===
    st.subheader("2. 题材热度与资金流向")
    
    if not df_themes.empty:
        # 只展示前15个大题材，避免图表太拥挤
        top_themes = df_themes.head(15)
        
        col_chart1, col_chart2 = st.columns(2)
        
        with col_chart1:
            st.markdown("**📊 题材热度排行 (涨停家数)**")
            fig1 = px.bar(
                top_themes, 
                x='题材', 
                y='涨停家数', 
                color='涨停家数',
                text='涨停家数',
                color_continuous_scale='OrRd',
                hover_data=['家数占比(%)']
            )
            fig1.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig1, use_container_width=True)
            
        with col_chart2:
            st.markdown("**💰 题材吸金排行 (总成交额)**")
            fig2 = px.bar(
                top_themes, 
                x='题材', 
                y='总成交额(亿)', 
                color='总成交额(亿)',
                text='总成交额(亿)',
                color_continuous_scale='Viridis', # 资金用冷色调区分
            )
            fig2.update_layout(xaxis_tickangle=-45)
            st.plotly_chart(fig2, use_container_width=True)

    # === 第三部分：题材详细归因 (核心功能) ===
    st.subheader("3. 题材梯队深度解析")
    st.markdown("👇 **点击题材标题**，查看该题材下的龙头梯队与资金分布")

    # 遍历题材数据
    for index, row in df_themes.iterrows():
        theme_name = row['题材']
        count = row['涨停家数']
        money = row['总成交额(亿)']
        high_board = row['高标高度']
        
        # 筛选出属于该题材的个股
        # 注意：这里做简单的字符串匹配，因为东方财富的归类已经是聚合过的
        # 如果你想做更模糊的匹配，可以使用 str.contains
        subset = df_stocks[df_stocks['题材'] == theme_name].copy()
        
        # *** 关键：按连板数降序排序 ***
        subset = subset.sort_values(by=['连板数', '封板资金(亿)'], ascending=[False, False])
        
        # 定义 Expander 的标题格式
        # 格式：[题材名] 🔥5家 | 💰20.5亿 | 🚀最高5板
        title = f"【{theme_name}】 🔥 {count}家 ({row['家数占比(%)']}%) | 💰 {money}亿 | 🚀 最高 {high_board}板"
        
        with st.expander(title):
            # 高亮样式
            def highlight_leader(s):
                is_leader = s['连板数'] == high_board
                color = '#ffebee' if is_leader else '' # 浅红色背景高亮龙头
                return [f'background-color: {color}' for _ in s]

            # 展示数据表
            # 选取展示的列
            display_cols = ['代码', '名称', '最新价', '涨跌幅', '连板数', '成交额(亿)', '封板资金(亿)', '换手率']
            valid_disp_cols = [c for c in display_cols if c in subset.columns]
            
            st.dataframe(
                subset[valid_disp_cols].style
                .format({'成交额(亿)': '{:.2f}', '封板资金(亿)': '{:.2f}', '最新价': '{:.2f}'})
                .apply(highlight_leader, axis=1), # 高亮龙头
                use_container_width=True,
                hide_index=True
            )

    # === 第四部分：全部数据查询 ===
    st.markdown("---")
    with st.expander("🔎 查看当日全部涨停明细 (支持搜索)"):
        search = st.text_input("输入股票代码或名称搜索:", "")
        df_display = df_stocks.copy()
        if search:
            df_display = df_display[df_display['名称'].str.contains(search) | df_display['代码'].str.contains(search)]
        
        st.dataframe(
            df_display.sort_values("连板数", ascending=False), 
            use_container_width=True
        )
