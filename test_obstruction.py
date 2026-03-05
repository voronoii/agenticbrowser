"""
Obstruction-Based Architecture 검증 스크립트

hogangnono.com에서 다음을 검증:
1. 페이지 로드 후 resolve_blocker()가 광고 팝업을 제거하는지
2. "로그인" 버튼에 대해 obstruction check가 하단 배너를 감지하는지
3. resolve_obstruction()이 배너를 CSS hide로 제거하는지
4. 배너 제거 후 일반 클릭이 가능한지
5. 상태 핑거프린트가 정상 동작하는지
"""

import asyncio
import sys

sys.path.insert(0, ".")

from src.core.browser import BrowserManager
from src.core.state import get_indexed_state


async def main():
    target_url = "https://hogangnono.com"
    print(f"=== Obstruction Detection Test ===")
    print(f"Target: {target_url}\n")

    browser = BrowserManager(headless=True)
    errors = []

    try:
        await browser.start()
        page = browser.page

        # 1. 페이지 이동
        print("1. 페이지 로드...")
        await browser.navigate(target_url)
        await asyncio.sleep(2)

        # 2. resolve_blocker: 광고 팝업 제거
        print("2. resolve_blocker() 실행...")
        blocker_result = await browser.resolve_blocker()
        print(f"   had_blocker: {blocker_result.get('had_blocker')}")
        print(f"   resolved: {blocker_result.get('resolved')}")
        print(f"   blocker_name: {blocker_result.get('blocker_name', '')[:60]}")
        print(f"   method: {blocker_result.get('method', '')}")

        if blocker_result.get("had_blocker") and blocker_result.get("resolved"):
            print("   => OK: 팝업 제거 성공")
        elif blocker_result.get("had_blocker") and not blocker_result.get("resolved"):
            errors.append("resolve_blocker()가 팝업을 감지했으나 제거 실패")
        else:
            print("   => INFO: 팝업 없음 (이미 제거되었거나 미노출)")

        await asyncio.sleep(1)

        # 3. 페이지 상태 추출
        print("\n3. 페이지 상태 추출...")
        state = await get_indexed_state(page)
        print(f"   요소 수: {len(state.elements)}개")
        print(f"   active_modal: {state.active_modal}")
        print(f"   modal_description: {state.modal_description}")

        # "로그인" 버튼 찾기
        login_elem = None
        for el in state.elements:
            if "로그인" in el.name:
                login_elem = el
                print(
                    f'   => 로그인 버튼 발견: [{el.index}] {el.role} <{el.tag}> "{el.name}"'
                )
                break

        if not login_elem:
            print("   => WARN: '로그인' 버튼을 찾지 못함")
            # 요소 목록 출력
            print("   요소 목록 (처음 20개):")
            for el in state.elements[:20]:
                print(
                    f'     [{el.index}] {el.role} <{el.tag}>: "{el.name[:40]}" (layer={el.layer})'
                )
        else:
            # 4. Obstruction check
            print(f"\n4. check_obstruction(aidx={login_elem.index})...")
            obstruction = await browser.check_obstruction(login_elem.index)
            print(f"   obstructed: {obstruction.get('obstructed')}")
            print(f"   reason: {obstruction.get('reason')}")
            if obstruction.get("obstructed"):
                blocker = obstruction.get("blocker", {})
                print(f"   blocker_selector: {blocker.get('selector', '')}")
                print(f"   blocker_tag: {blocker.get('tag', '')}")
                print(f"   blocker_text: {blocker.get('text', '')[:80]}")
                print(f"   blocker_position: {blocker.get('position', '')}")
                print(f"   blocker_zIndex: {blocker.get('zIndex', '')}")

                # 5. resolve_obstruction
                print(f"\n5. resolve_obstruction()...")
                resolve_result = await browser.resolve_obstruction(obstruction)
                print(f"   resolved: {resolve_result.get('resolved')}")
                print(f"   method: {resolve_result.get('method')}")

                if resolve_result.get("resolved"):
                    print("   => OK: 차단 요소 제거 성공")

                    # 차단 해소 후 다시 check
                    await asyncio.sleep(0.5)
                    recheck = await browser.check_obstruction(login_elem.index)
                    print(f"   recheck obstructed: {recheck.get('obstructed')}")
                    if not recheck.get("obstructed"):
                        print("   => OK: 재확인 — 차단 해소 검증 완료")
                    else:
                        errors.append("resolve_obstruction 후에도 여전히 차단됨")
                else:
                    errors.append(f"resolve_obstruction 실패: {resolve_result}")
            else:
                print("   => INFO: 차단 없음 — 로그인 버튼 클릭 가능")

            # 6. 상태 핑거프린트 테스트
            print(f"\n6. 상태 핑거프린트 테스트...")
            fp1 = await browser.get_state_fingerprint()
            print(
                f"   pre-click fingerprint: url={fp1.get('url', '')[:50]}, "
                f"has_modal={fp1.get('has_modal')}, "
                f"interactive_count={fp1.get('interactive_count')}"
            )

            # 로그인 버튼 클릭 시도
            print(f"\n7. 로그인 버튼 클릭 시도...")
            locator = page.locator(login_elem.selector)
            click_count = await locator.count()
            if click_count > 0:
                try:
                    await locator.first.click(timeout=5000)
                    print("   => 일반 클릭 성공!")
                except Exception as e:
                    print(f"   => 일반 클릭 실패: {e}")
                    # dispatchEvent 폴백 시도
                    try:
                        await locator.first.evaluate("""(el) => {
                            ['mouseenter', 'mouseover', 'mousedown', 'mouseup', 'click'].forEach(t => {
                                el.dispatchEvent(new MouseEvent(t, {
                                    bubbles: true, cancelable: true, view: window
                                }));
                            });
                        }""")
                        print("   => dispatchEvent 폴백 성공!")
                    except Exception as e2:
                        print(f"   => dispatchEvent 폴백도 실패: {e2}")
                        errors.append(f"로그인 버튼 클릭 실패: {e}")

                await asyncio.sleep(2)

                # 클릭 후 핑거프린트 비교
                fp2 = await browser.get_state_fingerprint()
                print(
                    f"\n   post-click fingerprint: url={fp2.get('url', '')[:50]}, "
                    f"has_modal={fp2.get('has_modal')}, "
                    f"interactive_count={fp2.get('interactive_count')}"
                )

                changed = (
                    fp2.get("url") != fp1.get("url")
                    or fp2.get("has_modal") != fp1.get("has_modal")
                    or fp2.get("focus_tag") != fp1.get("focus_tag")
                    or abs(
                        fp2.get("interactive_count", 0)
                        - fp1.get("interactive_count", 0)
                    )
                    > 3
                    or fp2.get("title") != fp1.get("title")
                )
                print(f"   state_changed: {changed}")
                if changed:
                    print("   => OK: 상태 변경 감지됨")
                else:
                    print("   => WARN: 상태 변경 미감지 — 클릭이 효과 없었을 수 있음")
                    errors.append("로그인 클릭 후 상태 변경 미감지")

                # 로그인 모달 확인
                state2 = await get_indexed_state(page)
                print(f"\n   post-click 요소 수: {len(state2.elements)}개")
                print(f"   active_modal: {state2.active_modal}")
                print(f"   modal_description: {state2.modal_description}")

                if state2.active_modal:
                    print("   => OK: 로그인 모달 오픈 확인!")
                    print("   모달 내 요소 (처음 10개):")
                    for el in state2.elements[:10]:
                        print(
                            f'     [{el.index}] {el.role} <{el.tag}>: "{el.name[:40]}"'
                        )
                else:
                    print("   => WARN: 모달 미감지")
                    # 요소 목록 출력
                    print("   요소 목록 (처음 15개):")
                    for el in state2.elements[:15]:
                        print(
                            f'     [{el.index}] {el.role} <{el.tag}>: "{el.name[:40]}"'
                        )

            else:
                errors.append(f"로그인 버튼 locator 매칭 실패 (count={click_count})")

        # 결과 요약
        print(f"\n=== 결과 ===")
        if errors:
            print(f"WARNING: {len(errors)}개 이슈:")
            for err in errors:
                print(f"   - {err}")
        else:
            print(f"OK: 모든 검증 통과!")

    except Exception as e:
        print(f"\nFATAL ERROR: {e}")
        import traceback

        traceback.print_exc()
        sys.exit(2)

    finally:
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
