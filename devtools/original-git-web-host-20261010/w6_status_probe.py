"""Synthetic-only actual Controller/Port Qt queue diagnostic; no WebEngine claim."""
import argparse
import json
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    output = args.output.absolute()
    if output.resolve() != output or not output.is_relative_to(HERE / '.runtime') or output.exists():
        parser.error('New task-local receipt required')
    sys.path[:0] = [str(ROOT), str(ROOT/'tests'), str(ROOT/'Open-LLM-VTuber/src')]
    from test_qt_web_existing_window import RealOwnerIOTests
    test = RealOwnerIOTests()
    test.setUpClass()
    result = dict(synthetic=True, native='UNVERIFIED')
    try:
        test.setUp()
        first = test.call('getState')
        test.fixture.enable_synthetic_pet()
        test.port.refresh_status()
        second = test.call('getState')
        result.update(firstCompleted=first.get('ok') is True, secondCompleted=second.get('ok') is True,
            petReady=second['capabilities']['pet']['state']=='ready',
            launcherHasVoice=isinstance(second['capabilities']['launcher'].get('voice'), dict),
            inflight=test.port.status_inflight, waiters=len(test.port.status_waiters),
            pending=len(test.port.broker.pending), connections=test.fixture.ws.connections)
    finally:
        test.doCleanups()
        result['timing'] = test.fixture.timing
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2), encoding='utf-8')
    return 0 if result.get('secondCompleted') and result.get('launcherHasVoice') else 2


if __name__ == '__main__': raise SystemExit(main())
