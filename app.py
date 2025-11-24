import streamlit as st
import akshare as ak
import pandas as pd
import plotly.express as px
import datetime

# --- 1. 页面配置 ---
st.set_page_config(page_title="A股复盘(调试增强版)", layout="wide", page_icon="🛠️")
st.markdown("""
    <style>
        .block-container {padding-top: 1rem;}
        .stExpander {border: 1px solid #ddd; border-radius: 5px;}
    </style>
""", unsafe_allow_html=True)

st.title("🛠️ A股涨停题材复盘 (增强容错版)")

# --- 2. 核心数据处理 ---

@st.cache_data(ttl=300)
def get_zt_data_robust(date_str):
    """
    增强版数据获取：自动适配列名，防止空白
    """
    status_text = st.empty()
    try:
        status_text.info(f"正在从东方财富获取 {date_str} 的数据...")
        
        # 获取原始数据
        df = ak.stock_zt_pool_em(date=date_str)
        
        if df is None or df.empty:
            status_text.warning(f"⚠️ 接口返回空数据！请检查 {date_str} 是否为交易日，或当前是否还没出数据。")
            return pd.DataFrame(), pd.DataFrame()

        # --- 调试关键点：打印原始列名 ---
        # 如果依然不出图，请截图这行显示的列名给我
        # st.write(f"🔧 调试信息 - 原始列名: {df.columns.tolist()}")

        # 1. 智能匹配“题材”列
        # 东方财富有时候叫'涨停原因类别'，有时候叫'所属行业'
        if '涨停原因类别' in df.columns:
            df['题材'] = df['涨停原因类别']
        elif '所属行业' in df.columns:
            df['题材'] = df['所属行业'] # 降级方案
        else:
            # 如果都没有，就给一个默认值，保证程序不崩
            df['题材'] = '未知题材'
        
        # 填充空值
        df['题材'] = df['题材'].fillna('其他')

        # 2. 智能匹配“连板数”列
        if '连板数' not in df.columns:
             # 有时候字段叫 '涨停统计'，里面是 '1/1' 这种格式
             if '涨停统计' in df.columns:
                 df['连板数'] = df['涨停统计'].apply(lambda x: int(str(x).split('/')[0]) if '/' in str(x) else 1)
             else:
                 df['连板数'] = 1 # 默认设为1

        # 3. 资金清洗
        def clean_amount(x):
            try:
                return float(x) / 100000000
            except:
                return 0.0
        
        # 优先用成交额，如果没有就用流通市值估算
        if '成交额' in df.columns:
            df['成交额(亿)'] = df['成交额'].apply(clean_amount)
        elif '流通市值' in df.columns and '换手率' in df.columns:
             # 估算：流通市值 * 换手率 / 100
             df['成交额(亿)'] = (pd.to_numeric(df['流通市值'], errors='coerce') * pd.to_numeric(df['换手率'], errors='coerce') / 100).apply(clean_amount)
        else:
            df['成交额(亿)'] = 0.0

        if '封板资金' in df.columns:
            df['封板资金(亿)'] = df['封板资金'].apply(clean_amount)
        else:
            df['封板资金(亿)'] = 0.0

        # 4. 聚合统计 (生成 df_themes)
        theme_stats = df.groupby('题材').agg(
            涨停家数=('名称', 'count'),
            总成交额=('成交额(亿)', 'sum'),
            最高板=('连板数', 'max')
        ).reset_index()
        
        # 增加占比
        theme_stats['占比'] = (theme_stats['涨停家数'] / len(df) * 100).round(1)
        theme_stats['总成交额(亿)'] = theme_stats['总成交额(亿)'].round(2)
        
        # 排序
        theme_stats = theme_stats.sort_values(by=['涨停家数', '总成交额(亿)'], ascending=[False, False])
        
        status_text.success("数据加载成功！")
        return df, theme_stats

    except Exception as e:
        status_text.error(f"数据处理报错: {e}")
        st.exception(e) # 打印详细报错堆栈
        return pd.DataFrame(), pd.DataFrame()

# --- 3. 侧边栏 ---
with st.sidebar:
    st.header("🎮 控制面板")
    if st.button("🔄 强制刷新"):
        st.cache_data.clear()
        st.rerun()
        
    # 默认选上一个交易日（避免今天还没开盘就没数据）
    default_date = datetime.date.today()
    if default_date.weekday() == 0: # 周一选上周五
         default_date -= datetime.timedelta(days=3)
    elif default_date.weekday() == 6: # 周日选周五
         default_date -= datetime.timedelta(days=2)
    elif default_date.weekday() == 5: # 周六选周五
         default_date -= datetime.timedelta(days=1)
    
    select_date = st.date_input("选择日期", default_date)
    date_str = select_date.strftime("%Y%m%d")

# --- 4. 主页面显示 ---

# 获取数据
df_stocks, df_themes = get_zt_data_robust(date_str)

if df_stocks.empty:
    st.error("❌ 当前没有数据。请尝试：\n1. 点击侧边栏“强制刷新”\n2. 切换日期（尽量选最近的一个交易日，如上周五）")
else:
    # 调试显示：如果图表还不出来，看这里是否列出了题材
    # st.write("前5个题材预览:", df_themes.head(5))

    # === 第一部分：概览 ===
    col1, col2, col3 = st.columns(3)
    col1.metric("📌 涨停总数", f"{len(df_stocks)}")
    col2.metric("💰 涨停总金额", f"{df_stocks['成交额(亿)'].sum():.1f} 亿")
    col3.metric("🚀 空间高度", f"{df_stocks['连板数'].max()} 板")

    # === 第二部分：图表 (确保有数据才画图) ===
    st.subheader("2. 题材热度与资金流向")
    
    if not df_themes.empty:
        # 取前15个
        top_plot = df_themes.head(15)
        
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("##### 🔥 题材家数排行")
            fig1 = px.bar(top_plot, x='题材', y='涨停家数', text='涨停家数', color='涨停家数', color_continuous_scale='Reds')
            st.plotly_chart(fig1, use_container_width=True)
        
        with c2:
            st.markdown("##### 💰 题材金额排行")
            fig2 = px.bar(top_plot, x='题材', y='总成交额(亿)', text='总成交额(亿)', color='总成交额(亿)', color_continuous_scale='Blues')
            st.plotly_chart(fig2, use_container_width=True)
    else:
        st.warning("⚠️ 题材统计为空，可能是由于无法识别'题材'列。")

    # === 第三部分：详细列表 ===
    st.subheader("3. 题材梯队深度解析")
    
    # 再次检查 df_themes
    if df_themes.empty:
        st.error("题材列表为空。")
    else:
        for idx, row in df_themes.iterrows():
            t_name = row['题材']
            t_count = row['涨停家数']
            t_money = row['总成交额(亿)']
            t_high = row['最高板']
            
            # 筛选该题材个股
            subset = df_stocks[df_stocks['题材'] == t_name].copy()
            # 排序：板数高 -> 封单大
            subset = subset.sort_values(by=['连板数', '封板资金(亿)'], ascending=[False, False])
            
            # 标题
            label = f"【{t_name}】 🔥{t_count}家 | 💰{t_money}亿 | 🚀最高{t_high}板"
            
            with st.expander(label):
                # 准备展示的列
                cols_to_show = ['代码', '名称', '最新价', '涨跌幅', '连板数', '成交额(亿)', '封板资金(亿)']
                # 过滤有效列
                final_cols = [c for c in cols_to_show if c in subset.columns]
                
                # 高亮龙头逻辑
                def highlight_top(s):
                    if s['连板数'] == t_high and t_high > 1:
                        return ['background-color: #ffebee'] * len(s)
                    return [''] * len(s)

                st.dataframe(
                    subset[final_cols].style.apply(highlight_top, axis=1).format("{:.2f}", subset=['成交额(亿)', '封板资金(亿)']),
                    use_container_width=True,
                    hide_index=True
                )
