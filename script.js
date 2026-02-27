var typingBool = false;
var typingIdx = 0;
var liIndex = 0;
var liLength = $(".typing-txt>ul>li").length;
// 타이핑될 텍스트를 가져온다
var typingTxt = $(".typing-txt>ul>li").eq(liIndex).text();
typingTxt = typingTxt.split(""); // 한글자씩 잘라 배열로만든다

if (typingBool == false) { // 타이핑이 진행되지 않았다면
    typingBool = true;
    var tyInt = setInterval(typing, 10); // 반복동작
}

function typing() {
    $(".typing ul li").removeClass("on");
    $(".typing ul li").eq(liIndex).addClass("on");
    if (typingIdx < typingTxt.length) { // 타이핑될 텍스트 길이만큼 반복
        $(".typing ul li").eq(liIndex).append(typingTxt[typingIdx]); // 한글자씩 이어준다.
        typingIdx++;
    } else { //한문장이끝나면
        if (liIndex < liLength - 1) {
            liIndex++;
            typingIdx = 0;
            typingBool = false;
            typingTxt = $(".typing-txt>ul>li").eq(liIndex).text();
            clearInterval(tyInt);
            setTimeout(function () {
                tyInt = setInterval(typing, 10);
            }, 100);
        } else if (liIndex == liLength - 1) {
            clearInterval(tyInt);
        }
    }
}
