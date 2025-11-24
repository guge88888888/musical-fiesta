import streamlit as st
import akshare as ak
import pandas as pd
import plotly.express as px
import datetime

# 设置页面配置
st.set_page_config(page_title="A股复盘神器", layout="wide", page_icon="📈")

# --- 核心函数：获取数据 (利用Streamlit缓存避免频繁请求) ---

@st.cache_data(ttl=600) # 设置缓存时间，10分钟失效，相当于手动刷新或定时更新
def get_sector_fund_flow():
    """
    获取东方财富板块资金流向
    """
    try:
        # 获取行业板块资金流向
        df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
        # 数据清洗
        df = df[['名称', '今日涨跌幅', '今日主力净流入', '今日超大单净流入']]
        
        # 将单位转换为“亿”
        def convert_unit(x):
            if '亿' in str(x):
                return float(x.replace('亿', ''))
            elif '万' in str(x):
                return float(x.replace('万', '')) / 10000
            return float(x)
            
        df['主力净流入(亿)'] = df['今日主力净流入'].apply(convert_unit)
        df['涨跌幅(%)'] = df['今日涨跌幅'].apply(lambda x: float(x.replace('%', '')))
        return df
    except Exception as e:
        st.error(f"获取资金数据失败: {e}")
        return pd.DataFrame()

@st.cache_data(ttl=600)
def get_limit_up_pool(date_str):
    """
    获取涨停板池及归因
    date_str: 格式 YYYYMMDD
    """
    try:
        # 东财涨停池
        df = ak.stock_zt_pool_em(date=date_str)
        if df.empty:
            return pd.DataFrame()
        
        # 选取关键列：代码、名称、最新价、涨跌幅、成交额、换手率、封板资金、涨停统计、连板数、所属行业
        # 注意：AkShare返回的列名可能会随源站更新而变动，需根据实际情况调整
        target_cols = ['代码', '名称', '最新价', '涨跌幅', '换手率', '封板资金', '连板数', '所属行业', '涨停原因类别']
        # 尝试筛选存在的列
        available_cols = [c for c in target_cols if c in df.columns]
        df = df[available_cols]
        return df
    except Exception as e:
        # 如果休市或数据未出，可能会报错
        return pd.DataFrame()

# --- 页面布局 ---

st.title("🚀 A股主力资金与涨停归因看板")
st.markdown("数据来源：AkShare (东方财富/新浪) | 自动/手动刷新")

# 侧边栏
with st.sidebar:
    st.header("控制面板")
    if st.button("🔄 手动刷新数据"):
        st.cache_data.clear()
        st.rerun()
    
    today = datetime.date.today()
    # 如果是周末，默认选周五
    if today.weekday() == 5:
        today -= datetime.timedelta(days=1)
    elif today.weekday() == 6:
        today -= datetime.timedelta(days=2)
        
    select_date = st.date_input("选择日期 (查看历史涨停)", today)
    date_str = select_date.strftime("%Y%m%d")

# --- 模块一：主力资金高低切换分析 ---
st.subheader("1. 主力资金高低切换侦测 (行业板块)")
st.info("💡 逻辑说明：\n- **低位潜伏 (左上)**: 板块跌但主力大买。\n- **高位接力 (右上)**: 板块涨且主力大买。\n- **高位出货 (右下)**: 板块涨但主力大卖。\n- **杀跌出逃 (左下)**: 板块跌且主力大卖。")

df_fund = get_sector_fund_flow()

if not df_fund.empty:
    # 制作散点图
    fig = px.scatter(
        df_fund,
        x="主力净流入(亿)",
        y="涨跌幅(%)",
        text="名称",
        color="主力净流入(亿)",
        color_continuous_scale="RdYlGn_r", # 红绿配色（注意国内是红涨绿跌，这里资金流出用绿，流入用红）
        size_max=60,
        hover_data=['今日超大单净流入'],
        template="plotly_white"
    )
    
    # 添加辅助线
    fig.add_vline(x=0, line_width=1, line_dash="dash", line_color="gray")
    fig.add_hline(y=0, line_width=1, line_dash="dash", line_color="gray")
    
    # 优化文字显示
    fig.update_traces(textposition='top center')
    st.plotly_chart(fig, use_container_width=True)
    
    with st.expander("查看资金流向详细数据"):
        st.dataframe(df_fund.sort_values("主力净流入(亿)", ascending=False).style.background_gradient(cmap='RdYlGn', subset=['主力净流入(亿)']))

else:
    st.warning("当前无法获取资金数据，可能是盘前或接口暂时不可用。")

# --- 模块二：涨停归因分析 ---
st.subheader(f"2. 涨停板事件驱动归因 ({select_date})")

df_zt = get_limit_up_pool(date_str)

if not df_zt.empty:
    # 1. 按行业/概念 聚合
    if '所属行业' in df_zt.columns:
        concept_counts = df_zt['所属行业'].value_counts().reset_index()
        concept_counts.columns = ['板块/概念', '涨停家数']
        
        col1, col2 = st.columns([1, 2])
        
        with col1:
            st.markdown("##### 🔥 热点板块排行")
            st.dataframe(concept_counts.head(10), hide_index=True)
        
        with col2:
            st.markdown("##### 📊 热点分布图")
            fig_bar = px.bar(concept_counts.head(15), x='板块/概念', y='涨停家数', color='涨停家数', color_continuous_scale='OrRd')
            st.plotly_chart(fig_bar, use_container_width=True)
    
    # 2. 详细归因表
    st.markdown("##### 📋 涨停详细归因")
    
    # 简单的搜索框
    search = st.text_input("🔍 搜索股票名称或原因", "")
    if search:
        df_zt = df_zt[df_zt['名称'].str.contains(search) | df_zt['所属行业'].str.contains(search) | df_zt['涨停原因类别'].str.contains(search)]

    # 对关键列进行高亮
    st.dataframe(
        df_zt.style.applymap(lambda x: 'color: red; font-weight: bold' if isinstance(x, (int, float)) and x > 9 else '', subset=['涨跌幅']),
        use_container_width=True,
        hide_index=True
    )
else:
    st.warning(f"{select_date} 暂无涨停数据，若是今日，请在收盘后查看，或检查日期是否为交易日。")