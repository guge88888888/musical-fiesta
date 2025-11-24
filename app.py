import streamlit as st
import akshare as ak
import pandas as pd
import plotly.express as px
import datetime

# --- 1. 页面基础设置 ---
st.set_page_config(page_title="A股复盘(免费版)", layout="wide", page_icon="📈")

# 隐藏一些恼人的默认菜单
st.markdown("""
    <style>
        #MainMenu {visibility: hidden;}
        footer {visibility: hidden;}
    </style>
""", unsafe_allow_html=True)

st.title("🚀 A股主力资金 & 涨停分析")
st.caption("部署环境：Streamlit Cloud (US) | 数据源：AkShare")

# --- 2. 核心函数 (带错误处理) ---

@st.cache_data(ttl=600)  # 缓存10分钟
def get_sector_fund_flow():
    """获取板块资金流向"""
    try:
        with st.spinner('正在连接东方财富接口获取资金数据...'):
            # 获取行业板块资金流向
            df = ak.stock_sector_fund_flow_rank(indicator="今日", sector_type="行业资金流")
            
            if df is None or df.empty:
                return pd.DataFrame()

            # 数据清洗
            df = df[['名称', '今日涨跌幅', '今日主力净流入', '今日超大单净流入']]
            
            # 单位转换函数
            def convert_unit(x):
                s = str(x)
                if '亿' in s:
                    return float(s.replace('亿', ''))
                elif '万' in s:
                    return float(s.replace('万', '')) / 10000
                return float(s) if s.replace('.','').replace('-','').isdigit() else 0.0
                
            df['主力净流入(亿)'] = df['今日主力净流入'].apply(convert_unit)
            df['涨跌幅(%)'] = df['今日涨跌幅'].apply(lambda x: float(x.replace('%', '')) if isinstance(x, str) else 0.0)
            return df
    except Exception as e:
        print(f"资金数据获取失败: {e}") # 打印到后台日志
        return pd.DataFrame()

@st.cache_data(ttl=600)
def get_limit_up_pool(date_str):
    """获取涨停数据"""
    try:
        with st.spinner(f'正在获取 {date_str} 涨停数据...'):
            df = ak.stock_zt_pool_em(date=date_str)
            if df is None or df.empty:
                return pd.DataFrame()
            
            # 筛选关键列
            target_cols = ['代码', '名称', '最新价', '涨跌幅', '换手率', '封板资金', '连板数', '所属行业', '涨停原因类别']
            # 这里的列名可能随接口更新变化，做个交集处理
            valid_cols = [c for c in target_cols if c in df.columns]
            return df[valid_cols]
    except Exception as e:
        print(f"涨停数据获取失败: {e}")
        return pd.DataFrame()

# --- 3. 侧边栏 ---
with st.sidebar:
    st.header("控制台")
    if st.button("🔄 强制刷新数据"):
        st.cache_data.clear()
        st.rerun()
    
    today = datetime.date.today()
    # 简单的逻辑：如果是周末，往前推到周五
    if today.weekday() == 5: today -= datetime.timedelta(days=1)
    elif today.weekday() == 6: today -= datetime.timedelta(days=2)
    
    select_date = st.date_input("选择日期", today)
    date_str = select_date.strftime("%Y%m%d")

# --- 4. 模块一：资金流向 ---
st.subheader("📊 主力资金：高低切换监测")

df_fund = get_sector_fund_flow()

if not df_fund.empty:
    # 散点图
    fig = px.scatter(
        df_fund,
        x="主力净流入(亿)",
        y="涨跌幅(%)",
        text="名称",
        color="主力净流入(亿)",
        color_continuous_scale="RdYlGn_r",
        height=600,
        template="plotly_white"
    )
    # 增加辅助线
    fig.add_vline(x=0, line_dash="dash", line_color="gray")
    fig.add_hline(y=0, line_dash="dash", line_color="gray")
    fig.update_traces(textposition='top center')
    
    # 修复警告：改用 theme="streamlit" 默认自适应
    st.plotly_chart(fig, use_container_width=True)
    
    with st.expander("查看详细数据表"):
        # 修复警告：改用 map 替代 applymap
        st.dataframe(
            df_fund.sort_values("主力净流入(亿)", ascending=False)
            .style.background_gradient(cmap='RdYlGn', subset=['主力净流入(亿)'])
            .format("{:.2f}", subset=['主力净流入(亿)', '涨跌幅(%)'])
        )
else:
    st.warning("⚠️ 资金数据加载失败。原因可能是：\n1. 此时是非交易时间，接口无数据。\n2. 云端服务器 IP 被东方财富暂时限制访问（常见于海外服务器）。")

# --- 5. 模块二：涨停归因 ---
st.subheader(f"🔥 涨停归因 ({date_str})")

df_zt = get_limit_up_pool(date_str)

if not df_zt.empty:
    # 搜索功能
    search = st.text_input("🔍 搜股票/概念 (例如: 华为)", "")
    if search:
        mask = df_zt.apply(lambda x: x.astype(str).str.contains(search, case=False).any(), axis=1)
        df_zt = df_zt[mask]

    # 热点聚合
    if '所属行业' in df_zt.columns:
        top_concepts = df_zt['所属行业'].value_counts().head(10)
        st.write("🔥 **当前最强板块:** " + " | ".join([f"{k}({v})" for k,v in top_concepts.items()]))

    # 样式处理函数
    def highlight_limit(val):
        # 简单的高亮逻辑
        if isinstance(val, (int, float)) and val > 9.5:
            return 'color: red; font-weight: bold'
        return ''

    # 修复警告：改用 map
    st.dataframe(
        df_zt.style.map(highlight_limit, subset=['涨跌幅']),
        use_container_width=True,
        hide_index=True
    )
else:
    st.info(f"📅 {date_str} 暂无涨停数据 (或是数据源暂时无法连接)。")
