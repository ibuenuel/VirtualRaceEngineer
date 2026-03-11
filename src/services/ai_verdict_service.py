"""
Module: services/ai_verdict_service.py
Responsibility: Generates human-readable "Race Engineer Verdicts" from
the combined outputs of all analysis strategies.

The service is intentionally heuristic-based and deterministic — no LLM
dependency. This makes outputs reproducible and the app runnable offline.
Architecture note: the class is designed as a Strategy-compatible service
so that a future LLMVerdictStrategy can replace or supplement it without
changing the calling code in main.py (see ADR-003).

Verdict structure:
  - Headline     : One-sentence winner/loser summary
  - Speed        : Where time was gained/lost (SpeedDelta)
  - Style        : Driver DNA comparison (aggressiveness, smoothness, brake profile)
  - Dominance    : Micro-sector control summary
  - Exits        : Overtake vulnerability / strength
  - Conclusion   : Overall engineering recommendation
"""

from dataclasses import dataclass, field

from src.services.analysis_engine import AnalysisResult


@dataclass
class Verdict:
    """Complete race engineer verdict for a two-driver comparison.

    Attributes:
        headline: Bold one-liner summarising the overall result.
        speed_analysis: Paragraph on time delta and where it was gained/lost.
        style_analysis: Paragraph on driving style differences.
        dominance_analysis: Paragraph on micro-sector control.
        overtake_analysis: Paragraph on corner exit strengths/weaknesses.
        conclusion: Overall engineering recommendation.
        driver_a: Three-letter code for Driver A.
        driver_b: Three-letter code for Driver B.
    """

    headline: str
    speed_analysis: str
    style_analysis: str
    dominance_analysis: str
    overtake_analysis: str
    conclusion: str
    driver_a: str
    driver_b: str
    raw_data: dict = field(default_factory=dict)


class AIVerdictService:
    """Generates a structured Race Engineer Verdict from analysis results.

    Usage:
        service = AIVerdictService()
        verdict = service.generate(
            driver_a="VER",
            driver_b="HAM",
            speed_result=speed_result,
            dna_result=dna_result,
            micro_result=micro_result,
            overtake_result=overtake_result,
        )
    """

    def generate(
        self,
        driver_a: str,
        driver_b: str,
        speed_result: AnalysisResult,
        dna_result: AnalysisResult,
        micro_result: AnalysisResult,
        overtake_result: AnalysisResult,
        name_a: str | None = None,
        name_b: str | None = None,
    ) -> Verdict:
        """Produce a full verdict from all four strategy outputs.

        Args:
            driver_a: Three-letter code for Driver A (used for data lookups).
            driver_b: Three-letter code for Driver B (used for data lookups).
            speed_result: Output of SpeedDeltaStrategy.
            dna_result: Output of DriverDNAStrategy.
            micro_result: Output of MicroSectorStrategy.
            overtake_result: Output of OvertakeProfileStrategy.
            name_a: Full display name for Driver A. Defaults to ``driver_a``.
            name_b: Full display name for Driver B. Defaults to ``driver_b``.

        Returns:
            A fully populated Verdict dataclass.
        """
        # Display names fall back to codes when full names are not provided
        n_a = name_a or driver_a
        n_b = name_b or driver_b

        sd = speed_result.summary
        dna = dna_result.summary
        ms = micro_result.summary
        op = overtake_result.summary

        profile_a = dna.get("driver_a_profile")
        profile_b = dna.get("driver_b_profile")

        return Verdict(
            driver_a=driver_a,
            driver_b=driver_b,
            headline=self._headline(driver_a, n_a, n_b, sd),
            speed_analysis=self._speed_analysis(driver_a, n_a, n_b, sd),
            style_analysis=self._style_analysis(driver_a, n_a, n_b, dna, profile_a, profile_b),
            dominance_analysis=self._dominance_analysis(driver_a, driver_b, n_a, n_b, ms),
            overtake_analysis=self._overtake_analysis(driver_a, driver_b, n_a, n_b, op),
            conclusion=self._conclusion(driver_a, n_a, n_b, sd, dna, ms, op),
            raw_data={
                "speed": sd,
                "dna": dna,
                "micro_sector": ms,
                "overtake": op,
            },
        )

    # ------------------------------------------------------------------
    # Section generators
    # ------------------------------------------------------------------

    @staticmethod
    def _headline(driver_a: str, n_a: str, n_b: str, sd: dict) -> str:
        faster_code = sd.get("faster_driver", driver_a)
        faster = n_a if faster_code == driver_a else n_b
        slower = n_b if faster_code == driver_a else n_a
        margin = sd.get("margin_s", 0.0)
        return (
            f"{faster} was the faster driver, building a {margin:.3f}s advantage "
            f"over {slower} across this lap."
        )

    @staticmethod
    def _speed_analysis(driver_a: str, n_a: str, n_b: str, sd: dict) -> str:
        faster_code = sd.get("faster_driver", driver_a)
        faster = n_a if faster_code == driver_a else n_b
        slower = n_b if faster_code == driver_a else n_a
        margin = sd.get("margin_s", 0.0)
        max_diff = sd.get("max_speed_diff_kph", 0.0)
        gain_sector = sd.get("biggest_gain_sector", "?")
        loss_sector = sd.get("biggest_loss_sector", "?")

        return (
            f"{faster} finished {margin:.3f}s ahead on this lap. "
            f"The peak speed differential was {abs(max_diff):.1f} km/h. "
            f"{faster} gained the most time in sector {gain_sector} "
            f"and lost the most in sector {loss_sector}."
        )

    @staticmethod
    def _style_analysis(
        driver_a: str, n_a: str, n_b: str, dna: dict, profile_a, profile_b
    ) -> str:
        if profile_a is None or profile_b is None:
            return "Driver DNA data unavailable."

        more_agg_code = dna.get("more_aggressive", driver_a)
        smoother_code = dna.get("smoother_driver", driver_a)
        more_agg = n_a if more_agg_code == driver_a else n_b
        smoother = n_a if smoother_code == driver_a else n_b

        # profile_a / profile_b may be DriverProfile objects or dicts
        def _get(p, key):
            return p[key] if isinstance(p, dict) else getattr(p, key)

        agg_a = _get(profile_a, "aggressiveness")
        agg_b = _get(profile_b, "aggressiveness")
        smooth_a = _get(profile_a, "smoothness")
        smooth_b = _get(profile_b, "smoothness")
        brake_a = _get(profile_a, "brake_profile")
        brake_b = _get(profile_b, "brake_profile")

        style_lines = []

        # Aggressiveness comparison
        agg_diff = abs(agg_a - agg_b)
        if agg_diff < 5:
            style_lines.append(
                f"Both drivers show a similar braking aggressiveness "
                f"({n_a}: {agg_a:.0f}/100, {n_b}: {agg_b:.0f}/100)."
            )
        else:
            style_lines.append(
                f"{more_agg} is the more aggressive braker "
                f"({n_a}: {agg_a:.0f}/100 vs {n_b}: {agg_b:.0f}/100)."
            )

        # Smoothness comparison
        smooth_diff = abs(smooth_a - smooth_b)
        if smooth_diff < 5:
            style_lines.append(
                f"Throttle application is equally smooth for both drivers "
                f"({n_a}: {smooth_a:.0f}/100, {n_b}: {smooth_b:.0f}/100)."
            )
        else:
            style_lines.append(
                f"{smoother} has a cleaner throttle trace "
                f"({n_a}: {smooth_a:.0f}/100 vs {n_b}: {smooth_b:.0f}/100)."
            )

        # Brake profile
        if brake_a == brake_b:
            style_lines.append(f"Both are classified as '{brake_a}' brakers.")
        else:
            style_lines.append(
                f"Braking style diverges: {n_a} is a '{brake_a}' "
                f"while {n_b} is a '{brake_b}'."
            )

        return " ".join(style_lines)

    @staticmethod
    def _dominance_analysis(driver_a: str, driver_b: str, n_a: str, n_b: str, ms: dict) -> str:
        total = ms.get("total_sectors", 0)
        if total == 0:
            return "Micro-sector data unavailable."

        wins_a = ms.get(f"sectors_won_{driver_a}", 0)
        wins_b = ms.get(f"sectors_won_{driver_b}", 0)
        dominant_code = ms.get("dominant_driver", driver_a)
        dominant = n_a if dominant_code == driver_a else n_b
        ratio = ms.get("dominance_ratio", 0.0)
        best_a = ms.get(f"best_sector_{driver_a}", "?")
        best_b = ms.get(f"best_sector_{driver_b}", "?")

        return (
            f"Across {total} micro-sectors of 50 m each, {n_a} won {wins_a} "
            f"and {n_b} won {wins_b}. "
            f"{dominant} controlled {ratio:.0f}% of the lap. "
            f"{n_a}'s strongest sector was #{best_a}; "
            f"{n_b}'s was #{best_b}."
        )

    @staticmethod
    def _overtake_analysis(driver_a: str, driver_b: str, n_a: str, n_b: str, op: dict) -> str:
        total = op.get("total_exit_zones", 0)
        if total == 0:
            return "Overtake profile data unavailable."

        wins_a = op.get(f"exit_wins_{driver_a}", 0)
        wins_b = op.get(f"exit_wins_{driver_b}", 0)
        stronger_code = op.get("stronger_on_exits", driver_a)
        stronger = n_a if stronger_code == driver_a else n_b
        avg_delta = op.get("avg_delta_kph", 0.0)

        vuln = n_b if stronger_code == driver_a else n_a

        return (
            f"Of {total} detected corner exits, {n_a} had the better exit "
            f"{wins_a} times and {n_b} {wins_b} times. "
            f"{stronger} is the stronger on exit overall (avg Δ {abs(avg_delta):.1f} km/h). "
            f"{vuln} is most vulnerable to being overtaken on the run to the next braking zone."
        )

    @staticmethod
    def _conclusion(
        driver_a: str,
        n_a: str,
        n_b: str,
        sd: dict,
        dna: dict,
        ms: dict,
        op: dict,
    ) -> str:
        faster_code = sd.get("faster_driver", driver_a)
        faster = n_a if faster_code == driver_a else n_b
        slower = n_b if faster_code == driver_a else n_a
        margin = sd.get("margin_s", 0.0)
        dominant_code = ms.get("dominant_driver", faster_code)
        stronger_exits_code = op.get("stronger_on_exits", faster_code)
        smoother_code = dna.get("smoother_driver", faster_code)

        strengths: list[str] = []
        if dominant_code == faster_code:
            strengths.append("track dominance")
        if stronger_exits_code == faster_code:
            strengths.append("corner exits")
        if smoother_code == faster_code:
            strengths.append("throttle application")

        strengths_text = (
            ", ".join(strengths) if strengths else "overall pace"
        )

        return (
            f"Engineering verdict: {faster} had the edge in {strengths_text}, "
            f"translating to a {margin:.3f}s margin over {slower}. "
            f"For {slower} to close the gap, focus areas are "
            f"{'braking commitment' if dna.get('more_aggressive') == faster_code else 'exit speed'} "
            f"and sector-level consistency."
        )
