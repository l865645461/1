"""A-module historical AIS replay and online-safe Port Status presentation."""

from datetime import timedelta
from html import escape
import json
from pathlib import Path
import sys

import pandas as pd
import streamlit as st
import streamlit.components.v1 as components

APP_DIR = Path(__file__).resolve().parent
if str(APP_DIR) not in sys.path:
    sys.path.insert(0, str(APP_DIR))

from data_loader import (SOURCES, get_port_call_bundle, inspect_sources,
                         list_mmsis, list_port_calls, pick_sample_port_call,
                         query_visit_ais, validate_links)
from map_utils import build_port_call_map, current_spatial_region
from replay_utils import (chain_intervals, current_ais_at_or_before,
                          events_as_replayed, history_at_or_before,
                          port_status_at_or_before, utc, visit_query_window)
from b_runtime_adapter import (lead_time_bin_ascii, load_predictions,
                               prediction_bundle, prediction_is_available)
from c_interface import build_c_interface_record
from c_results import c_result_for_replay, load_c_results
from c_diagnostics import candidates_for_port_call, load_c_diagnostics


STATUS_CARDS = [
    ("活跃船舶", "active_vessel_count", "最近AIS距当前快照不超过10分钟的船舶数量。"),
    ("外部接近区船舶", "approach_vessel_count", "当前位于研究定义External Approach区域的船舶数量。"),
    ("锚地区域船舶", "anchorage_present_count", "当前位于No.1 Anchorage官方边界内的船舶数量。"),
    ("确认锚泊等待", "anchorage_confirmed_waiting_count", "截至当前时刻已满足在线锚泊确认规则的船舶数量。"),
    ("Main泊位区确认活动", "berth_main_confirmed_occupied_count", "研究定义Main泊位区域内已满足在线稳定停留确认条件的船舶数量；不是官方泊位容量或泊位利用率。"),
    ("West泊位区确认活动", "berth_west_confirmed_occupied_count", "研究定义West泊位区域内已满足在线稳定停留确认条件的船舶数量；不是官方泊位容量或泊位利用率。"),
    ("近60分钟进港船舶", "unique_inbound_vessels_60m", "使用unique vessels，不是raw Gate crossing次数。"),
    ("近60分钟出港船舶", "unique_outbound_vessels_60m", "使用unique vessels，不是raw Gate crossing次数。"),
]

CASE_IDS = {
    "案例1｜节油情景完整（推荐）": "PC_202401_477166500_20240123T172010",
    "案例2｜锚泊后靠泊完整访问": "PC_202401_211886810_20240106T041143",
    "案例3｜直接靠泊完整访问": "PC_202401_538009831_20240101T235432",
    "案例4｜访问结束事件不完整": "PC_202401_414688000_20240101T021420",
}
LABEL_TEXT = {
    "direct": "直接靠泊 Direct",
    "indirect": "锚泊后靠泊 Indirect",
    "review": "待复核 Review",
    "not_eligible_no_ber": "未检测到正式BER",
}
EVENT_TEXT = {"ANC": "锚泊 ANC", "ARR": "到港 ARR", "BER": "靠泊 BER",
              "UNB": "离泊 UNB", "DEP": "离港 DEP"}


def utc_text(value):
    return "—" if value is None or pd.isna(value) else utc(value).strftime("%Y-%m-%d %H:%M:%S UTC")


def value_text(value, decimals=2):
    return "—" if value is None or pd.isna(value) else ("{:,." + str(decimals) + "f}").format(float(value))


def event_time_text(visible_events: pd.DataFrame, kind: str) -> str:
    rows = visible_events.loc[visible_events.event_type.eq(kind)].sort_values("event_time_utc")
    return "—" if rows.empty else utc_text(rows.iloc[0].event_time_utc)


def summary_event_display(formal_events: pd.DataFrame, visible_events: pd.DataFrame,
                          kind: str):
    """Distinguish a future formal event from an event absent from this visit."""
    visible = visible_events.loc[visible_events.event_type.eq(kind)].sort_values("event_time_utc")
    if not visible.empty:
        row = visible.iloc[0]
        note = "历史真值 · 当时尚未知" if row.get("replay_status") == "future" else None
        return utc_text(row.event_time_utc), note
    if formal_events.event_type.eq(kind).any():
        return "尚未发生 / 当前回放时刻尚不可见", None
    return "—", None


def interval_text(intervals, name: str) -> str:
    value = intervals.get(name)
    return "—" if value is None else "{:.2f} min".format(value)


def historical_stage(formal_events: pd.DataFrame, moment: pd.Timestamp) -> str:
    """Presentation-only stage from released historical event times."""
    by_type = {kind: formal_events.loc[formal_events.event_type.eq(kind)]
               for kind in EVENT_TEXT}
    for kind, stage in [("DEP", "已离港"), ("UNB", "已离泊"),
                        ("BER", "已靠泊"), ("ARR", "到港后进港／待靠泊")]:
        if not by_type[kind].empty and pd.to_datetime(
                by_type[kind].event_time_utc, utc=True).le(moment).any():
            return stage
    anc = by_type["ANC"]
    if not anc.empty:
        starts = pd.to_datetime(anc.event_time_utc, utc=True)
        ends = pd.to_datetime(anc.event_end_time_utc, utc=True)
        if ((starts <= moment) & (moment <= ends)).any():
            return "锚泊阶段"
        if (ends < moment).any():
            return "锚泊结束至到港"
    return "到港前航行"


def render_timeline(visible_events: pd.DataFrame) -> None:
    if visible_events.empty:
        st.info("此时刻尚未发生本次访问的正式事件。")
        return
    cards = []
    for event in visible_events.itertuples(index=False):
        future = event.replay_status == "future"
        title = escape(EVENT_TEXT[str(event.event_type)])
        when = escape(utc_text(event.event_time_utc))
        confidence = escape(str(event.confidence_level).capitalize())
        note = '<div class="a-timeline-note">历史真值 · 当时尚未知</div>' if future else ""
        cards.append('<div class="a-timeline-node{}"><div class="a-timeline-title">{}</div>'
                     '<div class="a-timeline-time">{}</div><div class="a-timeline-conf">{}</div>{}</div>'.format(
                         " future" if future else "", title, when, confidence, note))
    st.markdown("""
    <style>
    .a-timeline {display:flex;flex-wrap:wrap;gap:14px;align-items:stretch;margin:12px 0 20px}
    .a-timeline-node {min-width:158px;max-width:220px;flex:1;padding:15px 17px;
      border:1px solid #bed4e5;border-top:4px solid #2077a7;border-radius:9px;background:#f4f9fc}
    .a-timeline-node.future {border-color:#d5d8dc;border-top-color:#a3a8ae;
      background:#f3f4f5;color:#777e85}
    .a-timeline-title {font-weight:700;font-size:1rem}
    .a-timeline-time {font-size:.82rem;margin-top:9px;white-space:nowrap}
    .a-timeline-conf {font-size:.8rem;margin-top:5px}
    .a-timeline-note {font-size:.74rem;margin-top:8px}
    </style><div class="a-timeline">""" + "".join(cards) + "</div>", unsafe_allow_html=True)


def render_summary_cards(items) -> None:
    blocks = []
    for item in items:
        title, value = item[:2]
        note = item[2] if len(item) > 2 else None
        note_html = ('<div class="a-summary-note">{}</div>'.format(escape(str(note)))
                     if note else "")
        blocks.append('<div class="a-summary-card"><div class="a-summary-label">{}</div>'
                      '<div class="a-summary-value">{}</div>{}</div>'.format(
                          escape(str(title)), escape(str(value)), note_html))
    st.markdown("""
    <style>
    .a-summary-grid {display:grid;grid-template-columns:repeat(auto-fit,minmax(215px,1fr));
      gap:10px;margin:12px 0 8px}
    .a-summary-card {min-width:0;padding:11px 13px;border:1px solid #dde5eb;
      border-radius:8px;background:#fbfcfd}
    .a-summary-label {font-size:.82rem;color:#536779;margin-bottom:5px}
    .a-summary-value {font-size:.98rem;font-weight:600;color:#253443;
      overflow-wrap:anywhere;line-height:1.4}
    .a-summary-note {font-size:.74rem;color:#687787;margin-top:4px}
    </style><div class="a-summary-grid">""" + "".join(blocks) + "</div>", unsafe_allow_html=True)


def reveal_truth(value, event_time, replay_time, show_future_truth, *, suffix=""):
    """Reveal a historical target only once its corresponding event is reached."""
    if value is None or pd.isna(value):
        return "—", "unavailable/not applicable"
    reached = event_time is not None and not pd.isna(event_time) and utc(event_time) <= replay_time
    text = "{}{}".format(value, suffix)
    if reached:
        return text, "observed fact"
    if show_future_truth:
        return text, "历史真值 · 当时尚未知"
    return "—", "当前回放时刻尚未知"


def render_b_prediction_panel(*, call, label, replay_time, show_future_truth, predictions,
                              observed_chain, a_stage):
    """Present frozen B outputs while keeping historical truth visibly separate."""
    st.subheader("模型预测 · 历史回放")
    st.warning("历史回放预测，不代表实时生产部署结果。模型预测与正式历史事件、标签分层展示，不会混写。")
    cols = st.columns(3)
    arr_time = utc(call["arr_time_utc"])
    ber_time = None if pd.isna(call.get("ber_time_utc")) else utc(call["ber_time_utc"])

    with cols[0]:
        st.markdown("#### VAT 到ARR")
        vat = predictions.get("vat")
        if not prediction_is_available(vat):
            st.info("截至当前回放时刻，没有可用的预计算 VAT 预测。")
        else:
            st.metric("预测 VAT", "{:.2f} min".format(float(vat["prediction"])))
            st.caption("预测生成：{}；数据截至：{}".format(
                utc_text(vat["prediction_time_utc"]), utc_text(vat["data_available_until_utc"])))
            st.caption("预测剩余时间区间：{}（由预测值划分，非未来真值）".format(
                lead_time_bin_ascii(vat["prediction"])))
            actual_vat = (arr_time - utc(vat["prediction_time_utc"])).total_seconds() / 60
            if show_future_truth:
                st.write("历史实际 VAT：**{:.2f} min**".format(actual_vat))
                st.caption("历史真值 · 当时尚未知；仅用于离线评价")
                st.write("绝对误差：**{:.2f} min**".format(
                    abs(float(vat["prediction"]) - actual_vat)))
            else:
                st.write("历史实际 VAT：**—**")
                st.caption("离线历史真值默认隐藏，不进入B/C输入")
            st.caption("ARR event_id：{}；模型：{}；QC：{}".format(
                vat["event_id"], vat["model_version"], vat["qc_flag"]))

    with cols[1]:
        st.markdown("#### Direct / Indirect")
        direct = predictions.get("direct_indirect")
        is_high_trainable = (
            str(label.get("label_confidence")) == "high"
            and str(label.get("final_label")) in {"direct", "indirect"}
        )
        if not prediction_is_available(direct):
            st.info("截至当前回放时刻，没有可用的预计算 Direct/Indirect 预测。")
        else:
            st.metric("预测类别", str(direct["predicted_class"]))
            st.write("Indirect 概率：**{:.3f}**（阈值 {:.2f}）".format(
                float(direct["prediction"]), float(direct["decision_threshold"])))
            st.caption("预测生成：{}；数据截至：{}；概率未校准。".format(
                utc_text(direct["prediction_time_utc"]), utc_text(direct["data_available_until_utc"])))
            if is_high_trainable:
                if show_future_truth:
                    truth = LABEL_TEXT.get(
                        str(label["final_label"]), str(label["final_label"]))
                    st.write("历史正式标签：**{}**".format(truth))
                    st.caption("历史真值 · 当时尚未知；仅用于离线评价")
                    expected = "Direct" if str(label["final_label"]) == "direct" else "Indirect"
                    st.write("预测是否正确：**{}**".format("是" if direct["predicted_class"] == expected else "否"))
                else:
                    st.write("历史正式标签：**—**")
                    st.caption("离线历史真值默认隐藏，不进入B/C输入")
            else:
                st.write("历史正式标签：**不适用**")
                st.caption("仅对正式高置信、可训练的 Direct/Indirect 样本评价；Review 与 not_eligible_no_ber 不编码为 Direct。")
            st.caption("适用性：空间特征贡献较强，仅作为洋山港当前研究场景的历史回放展示。")

    with cols[2]:
        st.markdown("#### ARR 到 BER")
        wait = predictions.get("arr_to_ber")
        is_high_high = (
            str(call.get("arr_confidence_level")) == "high"
            and str(call.get("ber_confidence_level")) == "high"
        )
        if not prediction_is_available(wait):
            message = "该访问不属于 ARR=high 且 BER=high 的326条主模型适用样本。"
            if is_high_high:
                message = (
                    "ARR→BER预测暂未启用。为确保时间因果安全，本Demo仅在获得独立的"
                    "Gate到达信号后启用该预测；当前未提供该在线信号，因此不会使用事后"
                    "ARR记录代替实时触发。")
            st.info(message)
        else:
            st.metric("预测 ARR→BER", "{:.2f} min".format(float(wait["prediction"])))
            st.caption("预测生成：{}；数据截至：{}".format(
                utc_text(wait["prediction_time_utc"]), utc_text(wait["data_available_until_utc"])))
            actual, actual_note = reveal_truth(
                "{:.2f} min".format(float(call["arr_to_ber_min"])), ber_time,
                replay_time, show_future_truth)
            st.write("历史实际 ARR→BER：**{}**".format(actual))
            st.caption(actual_note)
            if actual_note != "当前回放时刻尚未知":
                st.write("绝对误差：**{:.2f} min**".format(
                    abs(float(wait["prediction"]) - float(call["arr_to_ber_min"]))))
            arr_conf, arr_conf_note = reveal_truth(call["arr_confidence_level"], arr_time,
                                                    replay_time, show_future_truth)
            ber_conf, ber_conf_note = reveal_truth(call["ber_confidence_level"], ber_time,
                                                    replay_time, show_future_truth)
            st.caption("ARR置信度：{}（{}）；BER置信度：{}（{}）".format(
                arr_conf, arr_conf_note, ber_conf, ber_conf_note))
            st.caption("模型：{}；长尾不确定性未量化；最终模型不含 Port Status 特征。".format(
                wait["model_version"]))

def render_c_panel(*, port_call_id, replay_time, show_future_truth, results):
    """Render C without recomputing A events, B models, or C frozen results."""
    st.subheader("PVAT对齐历史影子情景")
    st.warning(
        "本模块为离线历史影子决策/情景回放，不是港口正式调度。没有官方ETB/ETD、"
        "泊位计划、可航路线、船舶真实油耗曲线和港口授权，正式执行层保持“不建议执行”。")

    state = c_result_for_replay(results, port_call_id, replay_time)
    early = state.get("early")
    scenario = state.get("scenario")

    if state["reason"] == "port_call_not_in_frozen_c_evaluation_sample":
        st.info("当前Port Call不在冻结的262条提前决策评估样本中，不补造结果。")
    elif state["reason"] == "c_decision_not_yet_available":
        st.info("冻结决策尚未生成；可用时刻为 {}。不会提前显示未来结果。".format(
            utc_text(state["decision_time_utc"])))
    else:
        top = st.columns(4)
        top[0].metric("研究层建议", str(early["research_recommendation"]))
        top[1].metric("正式执行层", str(early["operational_advice"]))
        top[2].metric("冻结决策时刻", utc_text(early["decision_time_utc"]))
        top[3].metric("预测重算门禁", "通过" if bool(early["b_recompute_allowed"]) else "阻断")

        if not bool(early["b_recompute_allowed"]):
            st.error("未生成速度/RTA/燃油情景。阻断QC：{}。".format(
                early.get("b_blocking_qc_flags") or early.get("qc_flag")))
        elif scenario is None:
            st.info(
                "本条没有进入速度与燃油情景计算。冻结决策时航速为 {} kn；"
                "保持6–20 kn示例范围，不人为扩充可计算样本。".format(
                    value_text(early.get("current_speed_kn"))))
            st.caption("QC：{}；原因：{}".format(
                early.get("qc_flag"), early.get("research_recommendation_reason")))
        else:
            if str(early["research_recommendation"]) == "保持原方案":
                st.info(
                    "冻结研究结论为“保持原方案”。下方数值用于展示若采用PVAT对齐航速时的"
                    "参数化对比，不代表该船应当实际降速。")
            st.markdown("#### 参数化航速与低碳情景")
            saving_rate = (
                float(scenario["fuel_saved_t"]) / float(scenario["baseline_fuel_t"]) * 100
                if float(scenario["baseline_fuel_t"]) > 0 else 0.0)
            primary_metrics = st.columns(4)
            primary_metrics[0].metric(
                "当前速度", "{} kn".format(value_text(scenario["current_speed_kn"])))
            primary_metrics[1].metric(
                "建议速度（研究）", "{} kn".format(value_text(scenario["suggested_speed_kn"], 3)),
                delta="-{:.3f} kn".format(
                    float(scenario["current_speed_kn"]) - float(scenario["suggested_speed_kn"])))
            primary_metrics[2].metric(
                "情景节油量", "{} t".format(value_text(scenario["fuel_saved_t"], 4)),
                delta="{:.1f}%".format(saving_rate))
            primary_metrics[3].metric(
                "情景CO₂减排", "{} t".format(value_text(scenario["co2_reduced_t"], 4)),
                delta="{:.1f}%".format(saving_rate))

            fuel_metrics = st.columns(4)
            fuel_metrics[0].metric(
                "研究RTA候选", utc_text(scenario["recommended_rta_utc"]))
            fuel_metrics[1].metric(
                "可利用等待时间", "{} h".format(value_text(scenario["usable_wait_h"], 3)))
            fuel_metrics[2].metric(
                "原方案燃油", "{} t".format(value_text(scenario["baseline_fuel_t"], 4)))
            fuel_metrics[3].metric(
                "JIT情景燃油", "{} t".format(value_text(scenario["jit_fuel_t"], 4)))

            st.caption("RTA候选规则：**{}**".format(
                scenario["selected_rta_candidate_id"]))
            candidates = pd.DataFrame([
                ("Direct候选", scenario["direct_rta_candidate_utc"]),
                ("概率加权候选", scenario["probability_weighted_rta_candidate_utc"]),
                ("研究等待代理候选", scenario["indirect_wait_rta_candidate_utc"]),
                ("最终研究候选", scenario["recommended_rta_utc"]),
            ], columns=["RTA候选", "UTC时刻"])
            candidates["UTC时刻"] = candidates["UTC时刻"].map(utc_text)
            st.dataframe(candidates, use_container_width=True, hide_index=True)
            st.caption(
                "该结果属于基于预测Gate到达时间的PVAT对齐情景，不代表已经吸收锚泊等待。"
                "情景参数：Gate大圆距离×1.15；参考推进油耗2.0 t/h@12 kn；"
                "辅机0.2 t/h；等待使用未校准AIS/Port Status研究代理的保守下界。"
                "结果是参数化情景估算，不是实际节油减排。")

        with st.expander("追踪字段与研究边界"):
            st.write("决策AIS：{}；AIS age：{} min".format(
                utc_text(early.get("ais_time_utc")), value_text(early.get("ais_age_min"), 3)))
            st.write("Port Status快照：{}；age：{} min".format(
                utc_text(early.get("port_status_snapshot_time_utc")),
                value_text(early.get("port_status_age_min"), 3)))
            st.write("距离：{}；route_factor={}；质量标记={}".format(
                early.get("distance_method"), early.get("route_factor"),
                early.get("distance_quality")))
            st.write("模型范围：{}；部署状态：{}；训练方式：{}".format(
                early.get("model_usage_scope"), early.get("deployment_readiness"),
                early.get("temporal_training_mode")))
            st.caption("ARR→BER不包含ANC→ARR港外锚泊，也不假设全部等待均可消除。")

        historical = state.get("historical")
        if show_future_truth and historical is not None:
            st.markdown("#### 历史评价（历史真值 · 当时尚未知）")
            st.caption("该区域只作事后评价，不进入RTA、航速、燃油或CO₂计算。")
            hist_cols = st.columns(4)
            hist_cols[0].metric("历史验证", historical["historical_berth_jit_evidence_label"])
            hist_cols[1].metric(
                "实际ARR→BER", "{} min".format(
                    value_text(historical.get("actual_arr_to_ber_min_evaluation_only"), 3)))
            hist_cols[2].metric(
                "实际超额等待", "{} min".format(
                    value_text(historical.get("actual_excess_wait_min_evaluation_only"), 3)))
            hist_cols[3].metric(
                "事后oracle节油", "{} t".format(
                    value_text(historical.get("historical_oracle_fuel_saved_t_evaluation_only"), 4)))
        else:
            st.caption("如需查看独立的事后历史评价，请开启页面上方“显示完整历史真值事件链”。")

    with st.expander("PVAT对齐总体离线研究结果（不代表正式执行）"):
        report = results["report"]
        overview = st.columns(5)
        overview[0].metric("提前决策", report["early_decision_records"])
        overview[1].metric("可计算情景", report["eligible_scenarios"])
        overview[2].metric("影子推荐", report["research_shadow_recommendations"])
        overview[3].metric("PVAT对齐情景", 92)
        overview[4].metric("正式执行建议", report["execute_recommendations"])
        st.caption(
            "全样本参数化情景汇总（包含训练、验证和测试记录，不是独立测试效果）："
            "节油 {:.4f} t，CO₂减少 {:.4f} t；"
            "排除90条航速范围外与1条数据裁剪覆盖不足。".format(
                report["total_fuel_saved_t_scenario"],
                report["total_co2_reduced_t_scenario"]))
        st.image(str(results["figure"]), use_container_width=True)


def _diagnostic_metric(diagnostics, name, decimals=0):
    value = float(diagnostics["metrics"][name])
    return int(value) if decimals == 0 else round(value, decimals)


def render_wait_driven_jit_diagnostics(*, diagnostics, port_call_id):
    """Show the frozen diagnostic closure separately from PVAT scenarios."""
    st.subheader("等待驱动JIT可用性诊断")
    st.info(
        "本轮没有可用于等待驱动JIT情景的合格新增预测证据。合格样本为0；"
        "该结论仅适用于v1.2.1打包裁剪AIS和固定24小时离线筛选范围，"
        "不代表全量AIS中不存在提前降速机会。")
    cards = st.columns(5)
    cards[0].metric("诊断访问", _diagnostic_metric(diagnostics, "diagnostic_population"))
    cards[1].metric("找到候选时刻", _diagnostic_metric(
        diagnostics, "candidate_times_found_by_fixed_AIS_screen"))
    cards[2].metric("历史上下文完整", _diagnostic_metric(
        diagnostics, "candidate_times_with_complete_30min_A_context"))
    cards[3].metric("联合键精确核验", _diagnostic_metric(
        diagnostics, "B_exact_PortCall_candidateUTC_matches"))
    cards[4].metric("等待驱动合格样本", _diagnostic_metric(
        diagnostics, "currently_eligible_wait_driven_JIT_samples"))

    st.caption(
        "候选选择规则是离线回溯诊断，不是实时触发规则；联合键为"
        "Port Call ID + candidate UTC。最终ANC、ARR和历史标签不参与候选选择。")

    selected = candidates_for_port_call(diagnostics, port_call_id)
    if not selected.empty:
        st.markdown("#### 当前Port Call的更早候选诊断")
        view = selected[[
            "candidate_key", "c_candidate_time_utc", "c_candidate_distance_to_gate_nm",
            "c_ais_coverage_status", "b_checked_candidate_time_utc",
            "joint_key_match_status", "b_vat_status", "b_direct_indirect_status",
            "b_arr_to_ber_status", "follow_up_required",
        ]].rename(columns={
            "candidate_key": "联合键",
            "c_candidate_time_utc": "候选UTC",
            "c_candidate_distance_to_gate_nm": "距Gate近似距离_nm",
            "c_ais_coverage_status": "AIS覆盖",
            "b_checked_candidate_time_utc": "核验UTC",
            "joint_key_match_status": "联合键状态",
            "b_vat_status": "VAT状态",
            "b_direct_indirect_status": "Direct/Indirect状态",
            "b_arr_to_ber_status": "ARR→BER状态",
            "follow_up_required": "闭环状态",
        })
        st.dataframe(view, use_container_width=True, hide_index=True)
        alternate = selected["b_other_same_port_call_candidate_times_utc"].dropna()
        alternate = [str(value) for value in alternate if str(value).strip()]
        if alternate:
            st.warning(
                "同一Port Call另有历史替代候选 {}，已保留但不与原候选混同；"
                "禁止仅修改时间戳对齐已有特征。".format("；".join(alternate)))
    else:
        st.caption("当前Port Call不属于本轮4个更早候选；不会为其补造诊断结果。")

    with st.expander("查看全部4个候选及全链路测试口径"):
        all_candidates = diagnostics["reconciliation"][[
            "port_call_id", "mmsi", "c_candidate_time_utc",
            "c_ais_coverage_status", "b_checked_candidate_time_utc",
            "joint_key_match_status", "b_vat_status", "b_direct_indirect_status",
            "b_other_same_port_call_candidate_times_utc",
        ]]
        st.dataframe(all_candidates, use_container_width=True, hide_index=True)
        test_cols = st.columns(4)
        test_cols[0].metric("标记test情景", _diagnostic_metric(
            diagnostics, "B_Direct_test_marked_scenarios"))
        test_cols[1].metric("test子集节油情景", "{:.4f} t".format(
            _diagnostic_metric(diagnostics, "B_Direct_test_subset_fuel_saved_t", 4)))
        test_cols[2].metric("test子集CO₂情景", "{:.4f} t".format(
            _diagnostic_metric(diagnostics, "B_Direct_test_subset_co2_reduced_t", 4)))
        test_cols[3].metric("全链路独立测试确认", _diagnostic_metric(
            diagnostics, "full_chain_independent_test_confirmed"))
        st.caption(
        "预测结果中的test标记不自动等于全链路独立测试集；当前确认的全链路独立测试为0。")

    downloads = st.columns(2)
    downloads[0].download_button(
        "下载候选时刻联合键核对表",
        data=diagnostics["reconciliation"].to_csv(index=False).encode("utf-8-sig"),
        file_name="candidate_time_reconciliation.csv",
        mime="text/csv",
    )
    downloads[1].download_button(
        "下载全链路划分核对表",
        data=diagnostics["split_audit"].to_csv(index=False).encode("utf-8-sig"),
        file_name="full_chain_split_audit.csv",
        mime="text/csv",
    )


st.set_page_config(page_title="洋山港 JIT 历史回放", layout="wide")
st.markdown("""
<style>
/* 评审展示主题：深海蓝、港口青与低碳绿。 */
:root {
    --ocean-950: #071b2f;
    --ocean-900: #0b2945;
    --ocean-700: #105c86;
    --harbor-500: #0ea5a8;
    --green-500: #22a06b;
    --ink-900: #142235;
    --ink-600: #536578;
    --line: #dce6ef;
    --canvas: #f4f7fb;
}
.stApp { background: var(--canvas); color: var(--ink-900); }
.block-container { max-width: 1480px; padding-top: 1.5rem; padding-bottom: 4rem; }
[data-testid="stSidebar"] {
    background: linear-gradient(180deg, #f7fbff 0%, #edf4f8 100%);
    border-right: 1px solid #d9e5ed;
}
[data-testid="stSidebar"] .block-container { padding-top: 1.4rem; }
.jit-hero {
    position: relative;
    overflow: hidden;
    padding: 2.1rem 2.35rem 1.9rem;
    border-radius: 24px;
    color: white;
    background:
        radial-gradient(circle at 88% 20%, rgba(38, 190, 190, .30), transparent 28%),
        linear-gradient(125deg, #071b2f 0%, #0b3d62 58%, #0b6a72 100%);
    box-shadow: 0 18px 42px rgba(7, 27, 47, .18);
    margin-bottom: 1.15rem;
}
.jit-hero::after {
    content: "";
    position: absolute;
    width: 260px; height: 260px; right: -90px; bottom: -170px;
    border: 1px solid rgba(255,255,255,.20); border-radius: 50%;
    box-shadow: 0 0 0 30px rgba(255,255,255,.035), 0 0 0 60px rgba(255,255,255,.025);
}
.jit-eyebrow { font-size: .78rem; letter-spacing: .16em; font-weight: 750; opacity: .76; }
.jit-hero h1 { color: white; font-size: clamp(2rem, 3.5vw, 3.35rem); line-height: 1.08; margin: .5rem 0 .65rem; }
.jit-hero p { max-width: 800px; margin: 0; color: rgba(255,255,255,.80); font-size: 1rem; line-height: 1.7; }
.jit-tags { display:flex; gap:.55rem; flex-wrap:wrap; margin-top:1.25rem; }
.jit-tag { padding:.38rem .72rem; border-radius:999px; border:1px solid rgba(255,255,255,.22); background:rgba(255,255,255,.09); font-size:.78rem; }
.context-strip {
    display:grid; grid-template-columns:repeat(4,minmax(0,1fr)); gap:.7rem;
    margin:.85rem 0 .7rem;
}
.context-strip > div {
    background:white; border:1px solid var(--line); border-radius:14px;
    padding:.78rem .95rem; box-shadow:0 5px 16px rgba(25,58,84,.04);
}
.context-strip span { display:block; color:var(--ink-600); font-size:.76rem; margin-bottom:.22rem; }
.context-strip strong { display:block; color:var(--ink-900); font-size:.92rem; overflow-wrap:anywhere; }
.sidebar-brand { padding:.25rem 0 1rem; }
.sidebar-brand strong { color:#0b3d62; font-size:1.1rem; }
.sidebar-brand span { display:block; color:#647789; font-size:.82rem; margin-top:.25rem; }
h2, h3 { color: var(--ink-900); letter-spacing: -.015em; }
[data-testid="stMetric"] {
    background: rgba(255,255,255,.94);
    border: 1px solid var(--line);
    border-radius: 16px;
    padding: 1rem 1.05rem;
    min-height: 118px;
    box-shadow: 0 7px 20px rgba(25, 58, 84, .055);
}
div[data-testid="stMetricValue"] > div {
    font-size: clamp(1.25rem, 1.75vw, 1.85rem) !important;
    line-height: 1.18 !important;
    white-space: normal !important;
    overflow-wrap: anywhere !important;
    color: var(--ink-900) !important;
    letter-spacing: -.025em;
}
div[data-testid="stMetricLabel"] p {
    font-size: clamp(.82rem, 1vw, .98rem) !important;
    color: var(--ink-600) !important;
    font-weight: 650 !important;
}
div[data-testid="stMetricDelta"] > div {
    font-size: .92rem !important;
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    gap: .4rem; padding: .35rem; border-radius: 15px;
    background: #eaf1f6; border: 1px solid #d9e4ed;
}
[data-testid="stTabs"] button[role="tab"] {
    height: 44px; border-radius: 11px; padding: 0 1.15rem;
    color: #40576b; font-weight: 700;
}
[data-testid="stTabs"] button[role="tab"][aria-selected="true"] {
    background: white; color: #0b5c7d; box-shadow: 0 4px 12px rgba(30, 66, 91, .10);
}
[data-testid="stAlert"] { border-radius: 14px; border-width: 1px; }
[data-testid="stExpander"] { background:white; border:1px solid var(--line); border-radius:14px; }
[data-testid="stDataFrame"] { border:1px solid var(--line); border-radius:14px; overflow:hidden; }
.stButton > button, .stDownloadButton > button { border-radius: 11px; font-weight: 700; }
hr { border-color: #dfe8ef; }
@media (max-width: 900px) {
    .jit-hero { padding:1.55rem 1.35rem; border-radius:18px; }
    .context-strip { grid-template-columns:repeat(2,minmax(0,1fr)); }
}
</style>
""", unsafe_allow_html=True)
st.markdown("""
<section class="jit-hero">
  <div class="jit-eyebrow">YANGSHAN PORT · HISTORICAL SHADOW DECISION</div>
  <h1>洋山港 JIT 航速优化研究平台</h1>
  <p>将港口观测、冻结预测与低碳航速情景放在同一条时间轴上，展示单船从历史回放到节油与减排估算的完整证据链。</p>
  <div class="jit-tags">
    <span class="jit-tag">历史影子决策</span>
    <span class="jit-tag">时间因果安全</span>
    <span class="jit-tag">参数化情景估算</span>
    <span class="jit-tag">A_INTERFACE_V1.2.1</span>
  </div>
</section>
""", unsafe_allow_html=True)
st.info("展示定位：研究验证与历史回放，不替代港口正式调度。正式执行仍需官方泊位计划、可航路线、船舶真实油耗曲线及港口授权。")


@st.cache_data(show_spinner=False)
def source_summary():
    return inspect_sources(), validate_links()


@st.cache_data(show_spinner=False)
def mmsi_options():
    return list_mmsis()


@st.cache_data(show_spinner=False)
def port_calls_for(mmsi: str):
    return list_port_calls(mmsi)


@st.cache_data(show_spinner=False)
def selected_bundle(port_call_id: str):
    return get_port_call_bundle(port_call_id)


@st.cache_data(show_spinner=False, max_entries=8)
def selected_ais(mmsi: str, start: pd.Timestamp, end: pd.Timestamp):
    return query_visit_ais(mmsi, start, end)


@st.cache_data(show_spinner=False, max_entries=64)
def selected_status(replay_time_utc: pd.Timestamp):
    return port_status_at_or_before(SOURCES["port_status"], replay_time_utc)


@st.cache_data(show_spinner=False)
def frozen_b_predictions():
    return (load_predictions("vat"), load_predictions("direct_indirect"),
            load_predictions("arr_to_ber"))


@st.cache_data(show_spinner=False)
def frozen_c_results():
    return load_c_results()


@st.cache_data(show_spinner=False)
def frozen_c_diagnostics():
    return load_c_diagnostics()


try:
    source_summary()  # First-round read-only input and key-link validation.
    default_id = pick_sample_port_call()
    default_mmsi = str(selected_bundle(default_id)["port_call"]["mmsi"])
    mmsis = mmsi_options()
    st.sidebar.markdown(
        '<div class="sidebar-brand"><strong>历史回放控制台</strong>'
        '<span>选择案例、船舶与访问记录</span></div>',
        unsafe_allow_html=True)
    case_choice = st.sidebar.selectbox(
        "第一步 · 选择典型案例", ["自由选择"] + list(CASE_IDS), index=1,
        key="demo_case_choice_v2")
    st.sidebar.caption(
        "默认打开具有完整单船情景结果的案例。案例2展示锚泊后靠泊访问，"
        "案例3展示直接靠泊访问；案例4用于说明访问结束事件不完整的情况。")
    if case_choice == "案例4｜访问结束事件不完整":
        st.sidebar.info(
            "该访问缺少UNB（离泊）和DEP（离港）正式事件，用于展示数据不完整时的"
            "透明标记方式。系统不会使用未来数据或人为补齐缺失事件。")
    else:
        st.sidebar.caption(
            "部分访问可能因不在冻结评估样本、决策时刻尚未到达、AIS覆盖不足，或"
            "航速超出6–20 kn研究范围而不显示燃油情景。")
    if st.session_state.get("_last_case_choice") != case_choice:
        if case_choice in CASE_IDS:
            chosen_id = CASE_IDS[case_choice]
            st.session_state["demo_mmsi"] = chosen_id.split("_")[2]
            st.session_state["demo_port_call"] = chosen_id
        st.session_state["_last_case_choice"] = case_choice
    if st.session_state.get("demo_mmsi") not in mmsis:
        st.session_state["demo_mmsi"] = default_mmsi if default_mmsi in mmsis else mmsis[0]
    mmsi = st.sidebar.selectbox("第二步 · 选择船舶 MMSI", mmsis, key="demo_mmsi")
    visits = port_calls_for(mmsi)
    if visits.empty:
        st.warning("该MMSI没有已发布的Port Call")
        st.stop()
    visit_ids = visits.port_call_id.astype(str).tolist()
    visit_labels = {
        str(row.port_call_id): "{} · ARR {}".format(
            row.port_call_id, utc(row.arr_time_utc).strftime("%Y-%m-%d %H:%M UTC"))
        for row in visits.itertuples(index=False)
    }
    if st.session_state.get("demo_port_call") not in visit_ids:
        st.session_state["demo_port_call"] = default_id if default_id in visit_ids else visit_ids[0]
    port_call_id = st.sidebar.selectbox(
        "第三步 · 选择访问记录", visit_ids, key="demo_port_call",
        format_func=lambda item: visit_labels[item])
    with st.sidebar.expander("评委讲解建议", expanded=False):
        st.markdown(
            "1. 在“运行总览”查看当时港口状态与冻结预测。\n"
            "2. 在“JIT情景”查看单船航速、燃油和CO₂结果。\n"
            "3. 在“轨迹与事件”核对AIS轨迹和正式事件链。\n"
            "4. 在“数据与方法”查看诊断、接口与研究边界。")
    bundle = selected_bundle(port_call_id)
    call, label, events = bundle["port_call"], bundle["label"], bundle["events"]
    if str(call["mmsi"]) != mmsi or not events.port_call_id.eq(port_call_id).all():
        raise ValueError("MMSI / Port Call / formal event association mismatch")
    start, end, start_rule, end_rule = visit_query_window(events)
    with st.spinner("按MMSI和UTC访问窗口查询正式AIS…"):
        ais = selected_ais(mmsi, start, end)

    slider_start = start.tz_localize(None).to_pydatetime()
    slider_end = end.tz_localize(None).to_pydatetime()
    arr = utc(call["arr_time_utc"])
    slider_default = min(max(arr, start), end).tz_localize(None).to_pydatetime()
    st.subheader("时间回放")
    replay_input = st.slider("replay_time_utc（UTC；10 min步长）",
                             min_value=slider_start, max_value=slider_end,
                             value=slider_default, step=timedelta(minutes=10),
                             format="YYYY-MM-DD HH:mm:ss", key="replay_" + port_call_id)
    replay_time = pd.Timestamp(replay_input).tz_localize("UTC")
    show_future_truth = st.checkbox("显示完整历史真值事件链", value=False)
    vat_predictions, direct_predictions, wait_predictions = frozen_b_predictions()
    c_results = frozen_c_results()
    c_diagnostics = frozen_c_diagnostics()
    predictions = prediction_bundle(
        call, replay_time, vat_predictions, direct_predictions, wait_predictions)
    history = history_at_or_before(ais, replay_time)
    current, ais_age_min = current_ais_at_or_before(history, replay_time)
    snapshot, snapshot_age_min = selected_status(replay_time)
    with st.spinner("绘制截至回放时刻的轨迹及事件…"):
        map_view, map_info = build_port_call_map(
            SOURCES["geofence"], history, events, replay_time_utc=replay_time,
            include_future_truth=show_future_truth)
    chain = events_as_replayed(events, replay_time, include_future_truth=show_future_truth)
    observed_chain = events_as_replayed(events, replay_time, include_future_truth=False)
    if (map_info["max_ais_time_utc"] is not None and
            map_info["max_ais_time_utc"] > replay_time):
        raise AssertionError("Map used future AIS")
    if snapshot is not None and utc(snapshot["snapshot_time_utc"]) > replay_time:
        raise AssertionError("Port Status used a future snapshot")
    if current is not None and utc(current["timestamp_utc"]) > replay_time:
        raise AssertionError("Current position used future AIS")
    c_record = build_c_interface_record(
        port_call=call,
        replay_time_utc=replay_time,
        current_a_status=historical_stage(events, replay_time),
        observed_events=observed_chain,
        predictions=predictions,
        current_ais=current,
        ais_age_min=ais_age_min,
        port_status=snapshot,
        port_status_age_min=snapshot_age_min,
    )
except Exception as exc:
    st.error("只读历史回放加载失败：{}".format(exc))
    st.stop()

st.markdown(
    '<div class="context-strip"><div><span>当前船舶</span><strong>{}</strong></div>'
    '<div><span>访问类型</span><strong>{}</strong></div>'
    '<div><span>历史阶段</span><strong>{}</strong></div>'
    '<div><span>回放时刻</span><strong>{}</strong></div></div>'.format(
        escape(mmsi), escape(LABEL_TEXT.get(str(label["final_label"]), str(label["final_label"]))),
        escape(historical_stage(events, replay_time)), escape(replay_time.strftime("%Y-%m-%d %H:%M UTC"))),
    unsafe_allow_html=True)
st.caption("查询窗口：{} → {}（{}；{}）".format(
    utc_text(start), utc_text(end), start_rule, end_rule))

overview_tab, scenario_tab, track_tab, method_tab = st.tabs([
    "01 运行总览", "02 JIT情景", "03 轨迹与事件", "04 数据与方法"])

with overview_tab:
    st.subheader("港口运行快照")
    st.caption("所有状态均取自回放时刻及以前的数据，不使用未来AIS或未来Port Status。")
    cards = st.columns(4)
    for index, (title, field, help_text) in enumerate(STATUS_CARDS):
        cards[index % 4].metric(title, "—" if snapshot is None else str(int(snapshot[field])),
                                help=help_text)
    if snapshot is None:
        st.warning("当前回放时间之前没有Port Status快照；不使用未来快照填补。")
    else:
        st.caption("快照时间：{}　｜　回放时间：{}　｜　快照年龄：{:.2f} min".format(
            utc_text(snapshot["snapshot_time_utc"]), utc_text(replay_time), snapshot_age_min))
        if snapshot_age_min >= 10:
            st.error("Port Status快照超过正常10分钟粒度，需复核数据覆盖。")
        with st.expander("Gate穿越诊断（穿越次数，不代表船舶数量）"):
            st.write("近60分钟进港穿越次数：{}；近60分钟出港穿越次数：{}".format(
                snapshot["observed_inbound_gate_crossings_60m"],
                snapshot["observed_outbound_gate_crossings_60m"]))
            st.caption("同一船舶可能重复穿越，因此页面流量指标优先使用去重船舶数。")
    st.divider()
    render_b_prediction_panel(
        call=call, label=label, replay_time=replay_time,
        show_future_truth=show_future_truth, predictions=predictions,
        observed_chain=observed_chain, a_stage=historical_stage(events, replay_time))

with scenario_tab:
    render_c_panel(
        port_call_id=port_call_id, replay_time=replay_time,
        show_future_truth=show_future_truth, results=c_results)

with track_tab:
    st.subheader("当前船舶状态")
    st.caption("Port Call ID：{}　｜　MMSI：{}　｜　回放时刻：{}".format(
        port_call_id, mmsi, utc_text(replay_time)))
    if current is None:
        st.info("回放时刻以前在本访问查询窗口内尚无AIS；不伪造当前位置。")
    else:
        region = current_spatial_region(SOURCES["geofence"], current["lon"], current["lat"])
        st.write("当前AIS时间：**{}**　｜　AIS age：**{} min**　｜　当前空间区域：**{}**".format(
            utc_text(current["timestamp_utc"]), value_text(ais_age_min), region))
        vessel_cols = st.columns(4)
        for index, (title, value) in enumerate([
            ("当前经度", value_text(current["lon"], 6)),
            ("当前纬度", value_text(current["lat"], 6)),
            ("当前航速 SOG", "{} kn".format(value_text(current["sog_knots"]))),
            ("当前航向 COG", "{}°".format(value_text(current["cog_deg"]))),
        ]):
            vessel_cols[index % 4].metric(title, value)
        if ais_age_min > 10:
            st.warning("AIS状态可能过期；仅显示最后一个真实AIS点，不外推当前位置。")

    st.info("当前历史阶段：{}。仅依据已发布历史事件时间展示，不重新识别事件或预测。".format(
        historical_stage(events, replay_time)))
    st.subheader("空间轨迹与事件")
    components.html(map_view.get_root().render(), height=670, scrolling=False)
    st.caption("查询窗口AIS共{}点；截至回放时刻{}点；地图显示{}点（仅显示副本抽稀）。BER不伪造单点坐标。".format(
        len(ais), len(history), map_info["ais_display_count"]))
    st.caption("确定版GeoJSON已加载{}个对象。".format(len(map_info["geojson_objects"])))

    st.subheader("访问摘要")
    st.caption("离线访问标签为最终历史真值；未来事件默认隐藏，仅在开启完整历史真值后显示。")
    summary_intervals = chain_intervals(chain)
    label_raw = str(label["final_label"])
    summary_items = [
        ("MMSI", mmsi), ("Port Call ID", port_call_id),
        ("最终访问类型", LABEL_TEXT.get(label_raw, label_raw)),
        ("标签置信度", str(label["label_confidence"])),
    ]
    linked_anc = chain.loc[chain.event_type.eq("ANC")]
    if not linked_anc.empty:
        anc_text = "是（{}次）".format(len(linked_anc))
    elif events.event_type.eq("ANC").any() and not show_future_truth:
        anc_text = "—"
    else:
        anc_text = "否"
    summary_items.append(("关联锚泊 ANC", anc_text))
    summary_items.append(("到港 ARR", event_time_text(chain, "ARR")))
    for title, kind in [("靠泊 BER", "BER"), ("离泊 UNB", "UNB"), ("离港 DEP", "DEP")]:
        value, note = summary_event_display(events, chain, kind)
        summary_items.append((title, value, note))
    summary_items.extend((title, interval_text(summary_intervals, key)) for title, key in [
        ("锚泊结束至到港", "ANC end→ARR min"),
        ("到港至靠泊历时", "ARR→BER min"),
        ("靠泊至离泊历时", "BER→UNB min"),
        ("离泊至离港历时", "UNB→DEP min"),
    ])
    render_summary_cards(summary_items)

    st.subheader("船舶访问事件时间轴")
    st.caption("默认仅显示当时已经发生的正式事件；开启完整历史真值后，未来事件仅作为离线评价展示。")
    render_timeline(chain)
    with st.expander("查看详细事件数据"):
        if chain.empty:
            st.write("—")
        else:
            table = chain[["event_id", "event_type", "event_time_utc", "event_end_time_utc",
                           "confidence_level", "qc_flag", "replay_status", "replay_note"]].copy()
            def shade_future(row):
                style = "color: #9ca3af; background-color: #f3f4f6" if row["replay_status"] == "future" else ""
                return [style] * len(row)
            st.dataframe(table.style.apply(shade_future, axis=1),
                         use_container_width=True, hide_index=True)
    if show_future_truth:
        st.caption("灰色事件为历史真值 · 当时尚未知，不会进入当时的模型与决策输入。")

with method_tab:
    st.subheader("等待驱动JIT可用性诊断")
    st.caption("用于回答是否具备提前降速吸收锚泊等待的证据；诊断结果与PVAT对齐情景分开呈现。")
    render_wait_driven_jit_diagnostics(
        diagnostics=c_diagnostics, port_call_id=port_call_id)
    st.divider()
    st.subheader("接口导出与方法口径")
    st.download_button(
        "下载当前回放标准接口 JSON",
        data=json.dumps(c_record, ensure_ascii=False, indent=2, allow_nan=False),
        file_name="c_interface_{}_{}.json".format(
            port_call_id, replay_time.strftime("%Y%m%dT%H%M%SZ")),
        mime="application/json",
        help=("只包含截至当前回放时刻的观测与在线安全预测；"
              "不包含lead_time_min、未来事件或evaluation-only字段。"),
    )
    with st.expander("查看事件定义与数据边界", expanded=True):
        st.markdown("""
1. **到港 ARR**：船舶由海侧向港侧有效穿越研究定义 Arrival Gate。
2. **锚泊 ANC**：基于 No.1 官方锚地区域及低速持续停留规则识别。
3. **靠泊 BER**：基于 Main/West 研究泊位区域的稳定低速停留识别；不伪造单点坐标。
4. **离泊 UNB**：最终持续离开联合泊位区域。
5. **离港 DEP**：沿离港方向穿越与 ARR 相同的 Arrival Gate。
6. Port Status 每10分钟构建一次，只使用当时及以前的 AIS 信息。
7. No.1 Anchorage及Pilot Points来源于已有官方／公开空间定义；Arrival Gate、External Approach、Main/West为研究空间定义。
8. Main/West不是官方泊位边界，也不代表官方泊位容量或泊位利用率。

ARR/ANC/BER/UNB/DEP是离线确定版历史事件真值；Port Status是按当时可获得AIS构建的在线安全状态。地图AIS、当前AIS和Port Status快照均不得晚于回放时刻。""")

