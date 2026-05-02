# a, x, n = map(int, input("Enter a three numbers : ").split())

# result = pow(x + a, n)

# print(result)

score = int(input("Enter your score: "))
if score < 0:
    print("نمره وارد شده نا معتبر است ! ")
elif score > 20:
    print("نمره وارد شده نا معتبر است ! ")
elif score < 10:
    print("شما مردود شده اید !")
elif score > 10:
    print("شما قبول شده اید")
