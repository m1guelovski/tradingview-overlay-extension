from pathlib import Path

src_path = Path(__file__).with_name('strategy_family_stage1.py')
text = src_path.read_text(encoding='utf-8')
text = text.replace(
    '    per_2000_price_pnl: float\n    per_2000_swap: float\n    outcome: int\n',
    '    per_2000_price_pnl: float\n    per_2000_tp_potential: float\n    per_2000_swap: float\n    outcome: int\n',
)
text = text.replace(
    '            a = int(act_i[ai])\n            eligible = [m for m in range(key.start_band, 11) if a >= free_i[m]]\n',
    '            a = int(act_i[ai])\n            if int(df.index[a].year) != year:\n                continue\n            eligible = [m for m in range(key.start_band, 11) if a >= free_i[m]]\n',
)
text = text.replace(
    '                conv = float(q_usd[min(exit_i, len(q_usd)-1)])\n                price_pnl = ((exit_price-entry_level) if side == 1 else (entry_level-exit_price)) * 2000.0 * conv\n',
    '                conv = float(q_usd[min(exit_i, len(q_usd)-1)])\n                entry_conv = float(q_usd[min(entry_i, len(q_usd)-1)])\n                price_pnl = ((exit_price-entry_level) if side == 1 else (entry_level-exit_price)) * 2000.0 * conv\n                tp_potential = abs(target_level-entry_level) * 2000.0 * entry_conv\n',
)
text = text.replace(
    '                full.append(StagePath(symbol, -1, a, side, band, entry_i, exit_i, entry_level, exit_price, price_pnl, swap, outcome, terminal))\n',
    '                full.append(StagePath(symbol, -1, a, side, band, entry_i, exit_i, entry_level, exit_price, price_pnl, tp_potential, swap, outcome, terminal))\n',
)
text = text.replace(
    'max(1e-9,st.per_2000_price_pnl/0.02)',
    'max(1e-9,(st.per_2000_tp_potential-commission_rt)/0.02)',
)
exec(compile(text, str(src_path), 'exec'), globals())
