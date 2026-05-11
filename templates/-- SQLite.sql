-- SQLite

SELECT * FROM users WHERE email = 'johndoe@gmail.com';
UPDATE users 
SET password = 'scrypt:32768:8:1$xavv5E3OXhWJXAlT$96295fd6822020b280ef511b7515d162a4ce2f705b3e9101950f6cce3c78f9af69ce050460ed336b53e6c281f0d7c96790194b6c948e56b9d345b9c1629eefe6' 
WHERE email = 'johndoe@gmail.com';