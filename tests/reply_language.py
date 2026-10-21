"""Literal text of the reply-language rule that every copied agent prompt must carry.

The tests compare against these sentences instead of calling mapcore, so a prompt that drops the rule fails.
"""
REPLY={'en':('Reply to the user in the language of the current conversation.','If the user has explicitly asked for a language, use it.','Use {} only when the conversation language is unknown.','Saved results keep the language this request specifies.'),
       'ko':('사용자에게는 지금 대화에서 쓰는 언어로 답하세요.','사용자가 언어를 직접 정해 달라고 했으면 그 언어를 따르세요.','대화 언어를 알 수 없을 때만 {}로 답하세요.','저장하는 결과의 언어는 요청이 정한 대로 둡니다.')}
NAMES={'en':{'ko':'Korean','en':'English'},'ko':{'ko':'한국어','en':'영어'}}

def assert_reply_language(test,text,lang,written=None,*,saved_results=False):
    """lang is the app-selected fallback; written is the language the prompt itself is written in."""
    written=written or lang
    for line in REPLY[written][:3]:test.assertIn(line.format(NAMES[written][lang]),text)
    saved=REPLY[written][3]
    if saved_results:test.assertIn(saved,text)
    else:test.assertNotIn(saved,text)
