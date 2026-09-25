#!/usr/bin/env python3
"""facer_quips_gen.py — author docs/menus/expression-quips-en.json.

Reads the verbatim slot-3 dump of FACE2.DAT (JP preserved exactly), attaches the
English quip lines (below, dictionary-guided; names match dictionary/terms.json and
the shipped nameplates in docs/menus/expressions-en.json), and writes the fold input.

Records left with en_lines == [] keep the original JP bytes verbatim:
  * 21 unused 未表示 placeholder slots (never displayed)
  * REM's 4 Angelou-rune voice clips (206-209): a fictional runic font (<ANGELOUn>
    glyph codes), NOT natural-language text -> preserved verbatim.

Half-width budget: <=36 chars/line, <=3 lines (measured; box hard-clips ~38).
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# index -> list of English lines (half-width; <=36 chars/line, <=3 lines).
EN = {
# ---- JUSTIN ----
0: ["That's just harsh...", "Every single time,", "she wallops me, no holding back..."],
1: ["What is it, Sue?", "So you were watching, huh..."],
2: ["Nah, no good, no good...", "It's honestly all just junk...", "Guess my hunch was off..."],
3: ["...Heh heh!", "Say that AFTER you get a look", "at this, Gantz!!"],
4: ["Whoa! This old guy's a pain.", "I don't even like studying..."],
5: ["The pirates who attacked Dad", "and the others, what were they like?", "Tough men of the sea, I bet?"],
6: ["I'm putting my photo", "right here, everyone!"],
7: ["I finally made it this far...", "I've come...", "to claim the final answer."],
8: ["Owwww~~~!"],
9: ["Don't worry about me!", "A knuckle like that's nothing!", "Only natural for a top adventurer!!"],
10: ["We did it, Sue!", "That's number one!!"],
11: ["...I didn't mess it up!", "So why is my..."],
12: ["This treasure hunt's got", "a man's pride and an adventurer's", "soul riding on it!!"],
13: ["Is that birthday photo in here too?", "The cool one of me", "swinging my sword around!"],
14: ["My pocket's glowing!", "Don't tell me it's the Spirit", "Stone I stuck in there...!?"],
15: ["Ow, ow,", "owwww!!"],
16: ["I can't back down here!!", "To protect the people", "who survived!!"],
17: ["Mmmnh..."],
18: ["Yaaawn~~!", "Guess I'm a little short on sleep?", "All that grinding and snoring..."],
19: ["Jin said it too...", "The adventure from here is no game.", "Sue, you're staying behind."],
20: ["And what about YOUR future?", "Are you saying your future", "isn't here either!?"],
21: ["...Feena.", "J-just so I ask ahead of time...", "Feena, do you... about me...?"],
22: ["Mmm... just a little longer...", "Just till I count to ten..."],
23: ["Ughhh...", "Spinning, spinning...", "Alent's spinning..."],
24: ["Like I'd let myself", "die in a place like this!!"],
25: ["Return the light-god statue, Leen!", "It belongs to Luc village!!"],
26: ["Feena...", "Will she be all right?", "She's been asleep three days now..."],
27: ["W-well, you were the same, Feena!", "You looked plenty happy at the", "party! So we're even~~~!"],
28: ["What was I supposed to do~!", "I didn't know, okay~!"],
# ---- FEENA ----
29: ["Captain, will you introduce", "these two for me?"],
30: ["...", "Justin's dream", "will surely come true...!"],
31: ["...Oh, right, this is your first", "time on the New Continent..."],
32: ["Hee hee, thanks!!", "I'm full of energy now!", "And the treasure's all set, see?"],
33: ["Honestly, it gave me some trouble.", "One trap after another, a storm!", "Whoever built it has a nasty streak!"],
34: ["Kyaaah! Justin!!", "What are you doing!", "Hey, that's mine!!"],
35: ["I let you see me", "at my most uncool..."],
36: ["W-wait a second, Justin!", "Look over there!!"],
37: ["Justin!", "You're safe!"],
38: ["...That was awful, Justin.", "I... I was really worried", "about you..."],
39: ["Come, Justin...", "The long, sad destiny", "ends now."],
40: ["Justin, you pervert!", "I'm done with you!"],
41: ["Mmph~~ mmmph~~~", "Mmff mff, mmnngh~~~"],
42: ["Huh...?"],
43: ["Somehow, watching this", "is making ME embarrassed..."],
44: ["You take it too lightly, Justin!", "Adventuring isn't a child's game.", "One slip could cost you your life."],
45: ["Wash your own underwear for once!", "I keep telling you again and again,", "I have NO intention of marrying you!"],
46: ["...I finally remembered it.", "An adventurer is a free wind."],
47: ["Have you forgotten, Justin?", "An adventurer never gives up.", "That's what you told me."],
48: ["Huh... y-yes...", "Of course it's in there."],
49: ["Come to think of it, when did", "all these seagulls show up...?"],
50: ["I'm going to see the captain.", "Justin, Sue, you two had better", "head back to the crew's quarters."],
51: ["Let's go, Justin!", "Together, beyond the wind!!"],
52: ["I was just remembering...", "the first time I met you, Justin,", "was out here on the sea too..."],
53: ["This is my power...", "The power only I have,", "as an Icarian..."],
54: ["Let's go, Justin!", "Carrying everyone's hopes with us!"],
55: ["Hey, Justin...", "Do you... like me?"],
56: ["Stop it with the 'engagement'!", "Pakon just went and spread", "that rumor all on his own!!"],
57: ["Once an adventurer decides on", "something, they always push", "through any hardship!"],
58: ["Why do you sit so far away?", "Honestly, you're hopeless."],
59: ["...........Justin.", "That's not the kind of 'like'", "I was asking about..."],
60: ["Justin, you idiot!", "You... you made me...", "You made me cry!"],
61: ["Sister! Hold on!", "Please! Open your eyes, sister!!"],
62: ["Jus...tin...", "My body... ah! It's hot...", "...No! My body's... burning up!"],
63: ["Promise me, Justin.", "Never, ever pull something", "that reckless again. Please!"],
# ---- SUE ----
64: ["Come on, stop crying already.", "I'll help you look for it."],
65: ["I found it, of course I did!", "...Ta-daaa!!"],
66: ["Hmm...", "The cry of a black-tailed gull...?"],
67: ["No way am I doing it,", "being Gantz's bride!"],
68: ["Hey, hey, Porto,", "what are you doing all the way", "out here? Playing hide-and-seek?"],
69: ["...Justin, Justin,", "are you okay?", "That was a huge crash..."],
70: ["Somehow...", "a lot happened, but...", "it's like it was all a dream."],
71: ["...So, how'd it go?", "Did you find anything in that shed?"],
72: ["It's your own fault, Justin,", "for falling for Gantz's smooth talk", "and making a promise like that!"],
73: ["Kyaaaah!", "We're falling, faaalling!"],
74: ["Justin!", "The Spirit Stone's glowing again!"],
75: ["N-no, Justin!", "You'll be misunderstood, talking", "like that! The wallet, the wallet!"],
76: [".........", "...I'm not a child.", "I'm NOT a child!"],
77: ["But... but I don't want to...", "The last face of me you two", "remember would be a crying one..."],
78: ["Justin, you...", "TRAITOR!!"],
79: ["...Bye-bye! Do your best!", "I know you'll find your dream...", "You'll reach Angelou, Justin!"],
80: ["............", "...Hey, Justin.", "I'm just... kind of tired..."],
# ---- SUE (17, epilogue) ----
81: ["It's already been ten years", "since that long adventure ended..."],
82: ["Auntie Lilly!", "The ship's about to arrive!", "Hurry, hurry!"],
83: ["Ah, w-wait a second, you two...", "Could it be...?"],
# 84 PUFFY
84: ["Puu puu!"],
# ---- GADWIN ----
96: ["If you mean the pot, I ate it all.", "There's nothing left."],
97: ["Wah-hah-hah! It's fine, it's fine!", "Everyone makes mistakes."],
98: ["Well, as long as it doesn't rain,", "there's no problem at all..."],
99: ["Mm! A duel between men, is it?", "Very well! I accept your challenge!!", "I am Gadwin, knight of Dight!"],
100: ["Hear me, people of the wyverns!!", "Dight's dark clouds have lifted,", "for a hero has come, as of legend!"],
# ---- RAPP ----
101: ["Yo! Nicky!", "Good work bringing me word.", "Nice job, nice job!"],
102: ["Hahahaha!", "Look at you shakin', dummy!"],
103: ["I-idiot, don't be so loud!", "It's a secret from the others!"],
104: ["...Tch!", "I don't believe a word", "a woman says!!"],
105: ["Tch!", "Looks like you won't get it", "till you've been hurt..."],
106: ["...Hey.", "What kind of half-asleep", "nonsense are you spouting?"],
107: ["Hang on, Nicky!!", "I'm coming to save you!"],
# ---- MILDA ----
108: ["Rapp...", "I'm a Laine, you know.", "Is it okay for me to go with you?"],
109: ["...Is that so?", "Thanks, Rapp."],
110: ["Jus...tin, was it?", "Why didn't you", "finish me off?"],
111: ["That's it! Next time YOU", "come to Laine!", "I'll feed you something good!"],
112: ["Y-you're strong...", "Your... name...?"],
113: ["Don't you mock me...", "I'll tear you apart!!"],
114: ["Oh? A Cafu among you too...?", "...So you lot", "were in league with them!!"],
# ---- GUIDO ----
115: ["I'll have to make the round trip.", "Hmm, what a hassle."],
116: ["But... my medicine makes", "everyone healthy, and my wallet", "gets nice and warm too..."],
117: ["Hmm... I dropped the medicine off", "with Dr. Alma, but it still", "feels nowhere near enough."],
118: ["..........Ca...", "Carrot steak...*", "C-carrot...*"],
119: ["But everyone's becoming happy!", "Isn't that a wonderful thing?"],
120: ["Ugh, waaah!!"],
121: ["See, look!", "You're not alone at all, are you?", "THIS is your true power."],
# ---- MULLEN ----
128: ["Now then...", "let us begin our move as well.", "Move out, Leen!"],
129: ["It hasn't even been half an hour", "since we started.", "You seem weary, General Baal..."],
130: ["Ha-ha-ha-ha!", "Well, this is a surprise!!", "You really are an amazing boy!!"],
131: ["Leen's growing into the role", "of my aide rather nicely."],
132: ["I-impossible!?", "You're Justin!"],
133: ["Lieutenant Leen", "still stands ready here."],
134: ["...", "........."],
135: ["I'll say it once more, and that's", "the last time: hand over the", "Spirit Stone, Justin!"],
136: ["Now! Our Yggdrasil Plan", "is entering its final stage!", "Only the last piece remains!"],
137: ["If you activate that, countless", "soldiers will be caught in it!", "Father, have you lost your mind!?"],
# ---- LEEN ----
138: ["As we begin the operation,", "Colonel Mullen has words for us.", "All soldiers, listen well!"],
139: ["...No one's ever spoken to me", "like that before... It makes me", "happy..."],
140: ["Yes, Colonel Mullen."],
141: ["Ah...", "thank you so much,", "Lord Mullen."],
142: ["Garlyle Forces, Mullen Company,", "fall in! Eyes front!"],
143: ["Justin.", "The Icarians aren't as wonderful", "as you imagine them to be."],
144: ["That's... right.", "You're an adventurer, after all.", "From me, this means nothing..."],
145: ["A-a frog, no...", "Stay awaaay~~~!"],
146: ["Please, Feena! Lend me your power!", "Now is when I want to help the", "Colonel, now that he's suffering!"],
147: ["Aaaah!", "L-Lord Mullen!"],
148: ["I don't think I'll ever", "forget you..."],
149: ["You're right... No one falls", "into as many things as you do.", "A true top adventurer, Justin."],
150: ["Falling from way up there", "and calling it lucky...", "Hee, you're a strange one."],
151: ["Ahahaha!", "Only YOU would say that!!", "I was absolutely terrified."],
152: ["...Lord Mullen...?"],
# ---- BAAL ----
153: ["Mullen.", "Where are we now?"],
154: ["I've told you time and again,", "Mullen. When no soldiers are about,", "you may call me Father."],
155: ["Mmm...", "it seems...", "I dozed off for a little while..."],
156: ["Heh heh heh...", "How like you, that answer..."],
157: ["You brat! Don't get cocky!!", "I'll show you my true form...", "the power of the great Gaia!"],
158: ["Praise it! My power!!", "Submit! To Gaia!!"],
# ---- LILLY ----
160: ["Come to think of it, even when", "we first met, your father wore that", "stone round his neck so dearly..."],
161: ["Ahahaha! Don't worry, Sue.", "Justin's head couldn't possibly", "get any worse than it is!"],
162: ["Don't come into my kitchen", "all covered in mud!", "How many times must I say it!!"],
163: ["He's still a child now, but...", "in a few more years I wonder if", "Justin will set off adventuring too."],
164: ["Honestly, what a troublesome boy.", "He never helps out,", "yet always sneaks into my kitchen."],
165: ["So impressed was the pirate chief", "by your father's nerve that day,", "he decided to give up the trade!"],
166: ["Oh, that's too funny...", "You made me laugh so hard", "the tears are coming out..."],
# ---- CURATOR ----
167: ["Oho! You've come at the perfect", "time. Take a look at this, Justin!"],
168: ["A new Icarian statue!", "The restoration's just finished!"],
169: ["The Angelou god handed down", "in Parm..."],
# ---- GANTZ ----
170: ["At that rate you'll never find", "the Four Treasures by sundown.", "This duel goes to me!"],
171: ["Yo, Justin!", "Took you long enough, didn't it?", "And you call yourself top-class!!"],
172: ["Of course not!!", "As if the great Gantz would ever", "hang out with a guy like Justin!!"],
# ---- TENTZ ----
173: ["Uh-oh!", "It's Justin!!"],
174: ["Sniff, sniff... waaah, waaah!", "Waaaaaaaah!"],
# ---- KOZURU ----
175: ["Listen up, Justin.", "I hid the Four Treasures all over", "the place in northern Parm."],
# ---- GOOSE ----
176: ["Yaaawn~ mm... mumble mumble...", "I don't really get it, but", "I surrender, huh, Justin?"],
# ---- GANTZ MOM ----
177: ["Oh, if it isn't Justin.", "Weren't you supposed to be", "with our Gantz?"],
# ---- GONTZ ----
178: ["Huh, if it isn't Justin!?", "It's me, Gantz's big brother,", "Gontz!"],
# ---- JIN ----
179: ["Fwahahaha! You let it slip, boys!", "You can't let your guard down", "for a single second, hee!"],
180: ["Heeey!! Who's there!?", "Who's barging into my castle", "without my leave!!"],
181: ["Kah-kah-kah! Now this is priceless!", "Ee-hee-hee-hee!"],
182: ["I'm still going strong and", "active, I'll have you know!"],
# ---- CAPTAIN ----
183: ["This is a problem...", "Stowaways this small,", "I've never seen before..."],
184: ["...It's no use, we're done for!", "To think a real ghost ship", "would appear!! We'll all die here!"],
185: ["Ah, welcome.", "I'm the captain of this ship.", "Is there something you need, guest?"],
# ---- PAKON ----
186: ["I'm the head of the Adventurers'", "Guild, the great Pakon, yoyoyon~!", "What do you want with me?"],
187: ["H-h-how terribly rude!", "You are absolutely never joining", "the Adventurers' Guild, yon!"],
188: ["Waaah, waaah!", "How could you do this, yoyon!!", "My wedding's completely ruined~!"],
# ---- CLERK ----
189: ["Welcome, come right in!", "What sort of adventure", "are you looking for?"],
# ---- SAKI ----
192: ["Captain! Lieutenant Saki and the", "Lightning Star squad, all present!"],
193: ["Listen up! You came all the way", "from the New Continent, so don't", "show up empty-handed and shame us!"],
194: ["Right, right! Let's catch them", "quick and put them to torture,", "and then..."],
195: ["Ah!", "And they've even got", "a demi-human kid with them!"],
196: ["Ahh... could this", "possibly be... love?"],
# ---- NANA ----
197: ["Captain! Lieutenant Nana and the", "Bloody Rose squad have assembled."],
198: ["What an eyesore she is!", "That Leen...", "why does she tag along every time!"],
199: ["Oh-ho-ho-ho-ho!!"],
200: ["Hey now!", "What is the meaning of this!?"],
201: ["It's fine! I'll swear my men to", "silence and keep it hidden", "from Lord Mullen!"],
# ---- MIO ----
202: ["Captain! Lieutenant Mio and the", "Desert Moon squad are all here."],
203: ["How troubling. By my schedule,", "the three of you weren't set", "for execution until tomorrow..."],
204: ["My, Saki...", "why must you always", "think with your muscles?"],
# ---- REM ----
205: ["Are you okay!?", "...Sorry, big brothers.", "Was it really that bad?"],
# 206-209 Angelou runes -> keep verbatim
# ---- LUC ELDER ----
210: ["I am the elder of this Luc village.", "You saved Rem, I hear.", "The village thanks you deeply..."],
# ---- DIGHT ELDER ----
211: ["...Hm? You there?", "I'm the elder of this village...", "Is there something you need?"],
# ---- ALMA ----
212: ["I am Alma.", "I serve as a physician in", "the village of Dight up ahead."],
213: ["Well, this child seems well again,", "so I'll head back to Dight.", "I leave the rest to you, Gadwin."],
214: ["Good grief, Gadwin...", "That side of you hasn't changed", "one bit since we were children..."],
# ---- GUMBO ELDER ----
215: ["...Not yet? Then right here and now,", "go on and share a kiss.", "Come now, don't be shy, smooch!"],
216: ["Oho, brave couple!", "Did you enjoy", "the Gumbo festival?"],
# ---- NAINA ----
217: ["Ahh... Danda...", "Danda... Danda...", "Danda, Danda, Danda, Dandaa*"],
218: ["You two really are", "such a wonderful couple.", "We should follow their lead, Danda!"],
219: ["Hee hee hee... A truly great couple", "just has to get their hands on", "Gumbo's special matching goods~*"],
# ---- DANDA ----
220: ["N-no, um, well...", "That was just me talking to myself,", "so please, just forget you heard it!"],
221: ["There's a girl named Naina", "in this house, and she's", "incredibly cute."],
222: ["From now on, anytime, anywhere,", "let's always be together, Naina!", "I'll never, ever let you go!"],
# ---- LIETE ----
224: ["Now, Justin, show me...", "the moment the door to a new", "world swings open with a sound..."],
225: ["The chains of fate are coming", "loose. It seems I'll be able to", "record it upon my stone tablet."],
226: ["The barn I saw in a book", "was far more plain and humble..."],
227: ["Now go forth, brave hero!", "Now is the time to carve", "a new page into human history!!"],
228: ["To witness the future you create...", "perhaps that is what it means", "for me to create my own future."],
229: ["A world freed from the sad wheel", "of fate, a world one can walk", "by one's own will... And I saw it."],
230: ["Now... go on your way.", "I am Liete of Alent,", "one who waits through eternity."],
231: ["Welcome...", "bearer of the Spirit Stone,", "sign of the human-spirit pact..."],
# ---- MERMAID ----
232: ["That's right... All of us", "were captured by those brutes...", "Only I managed to escape."],
233: ["Please, oh brave hero,", "save everyone!"],
# ---- NICKY ----
234: ["Hm? What do you want?", "I don't know your faces.", "The password..."],
235: ["My name's Nicky.", "Believe it or not, I'm big brother", "Rapp's number-one apprentice!"],
236: ["Ah! Your ears are short!"],
# ---- NAZARI ----
237: ["Hmm, I see. It's no wonder", "you're mistaken. You closely", "resemble the folk of the tower."],
# ---- ALKADA (Orba) ----
238: ["Welcome to the tent of Orba", "the fortune-teller... Here is where", "the path each must walk is shown..."],
239: ["Oh, welcome.", "Staying the night today?"],
# ---- CHITT ----
240: ["Ah! You really are here!", "Hey, you're the one, aren't you?", "The one with the Spirit Stone."],
# ---- DARLIN ----
241: ["Same here.", "If Milda isn't napping beside me,", "I can't settle even to read a book."],
242: ["If so, it may have some link to", "how the Angelou civilization", "vanished from this world long ago..."],
243: ["Ahem! No, do excuse me,", "excuse me..."],
# ---- DERLIN ----
244: ["Stir in the sulfur extract~", "Mogi root, Lulu leaf, hmm-hmm~*", "Finish it off, plop... ...you here?"],
# ---- DORLIN ----
245: ["Fwahahaha, ha-ha-ha-ha!!", "REVIIIIVED!!"],
246: ["Nnngghhh!!", "I-I am, I am!!", "...Wait, who am I again?"],
# ---- PARATO ----
247: ["Justin's the best!", "Justin's the best!"],
# ---- GHOST ----
248: ["This is a place overflowing", "with curses and sorrow...", "That is why this darkness lingers..."],
249: ["Ah, travelers...", "If your hearts are strong,", "please hear my wish..."],
250: ["Thanks to you, I've been freed", "from the curse of the sword...", "Thank you so very much."],
# ---- KID GIRL ----
251: ["We get to eat really", "delicious food, right?", "I'm getting so hungry~"],
# ---- KID BOY ----
252: ["Yay! We've reached Parm!", "Where abouts is the", "'Seagull Inn' from here?"],
# ---- LORD (unused in main story) ----
253: ["*Not used in the main story", "Lord of the Mirage Castle:", "under the curse of the sword."],
254: ["*Not used in the main story", "Lord of the Mirage Castle:", "seized by the sword, attacking!"],
255: ["*Not used in the main story", "Lord of the Mirage Castle:", "the sword's curse broken, at ease."],
}


def main():
    dump = json.load(open(sys.argv[1] if len(sys.argv) > 1 else
                          ROOT / "work/pQUIP/dump_check.json"))
    recs = dump["records"]
    out = {"records": []}
    for r in recs:
        i = r["i"]
        out["records"].append({
            "i": i, "ctrl": r["ctrl"], "jp": r["jp"], "lines": r["lines"],
            "en_lines": EN.get(i, [])})
    outp = ROOT / "docs/menus/expression-quips-en.json"
    json.dump(out, open(outp, "w"), ensure_ascii=False, indent=1)
    n = sum(1 for r in out["records"] if r["en_lines"])
    print(f"wrote {outp}: {len(out['records'])} records, {n} translated")


if __name__ == "__main__":
    main()
