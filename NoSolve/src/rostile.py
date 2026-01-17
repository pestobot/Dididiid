import random

class Rostile:
    @staticmethod
    def get_solution(challenge_id) -> dict:
        start_timestamp = random.uniform(7000, 20000)
        amount_of_movements = random.randint(10, 100)

        click_x, click_y = random.randint(778, 1136), random.randint(499, 544)

        current_x, current_y = random.randint(500, 800), random.randint(200, 500)
        current_timestamp = start_timestamp

        mouse_movements = []

        for _ in range(amount_of_movements):
            increase_x, increase_y = random.choice([True, False]), random.choice([True, False])

            if current_x + 15 < 1910:
                increase_x = False
            if current_x - 15 < 2:
                increase_x = True
            
            if current_y + 15 < 1910:
                increase_y = False
            if current_y - 15 < 2:
                increase_y = True

            if increase_x:
                current_x += random.randint(1, 3) if random.random() <= 0.7 else random.randint(4, 15)
            else:
                current_x -= random.randint(1, 3) if random.random() <= 0.7 else random.randint(4, 15)

            if increase_y:
                current_y += random.randint(1, 3) if random.random() <= 0.7 else random.randint(4, 15)
            else:
                current_y -= random.randint(1, 3) if random.random() <= 0.7 else random.randint(4, 15)

            mouse_movements.append({"x": current_x, "y": current_y, "timestamp": current_timestamp})

            current_timestamp += random.uniform(10, 60)

        solution = {
            "challengeId": challenge_id,
            "solution": {
                "buttonClicked": True,
                "click": {
                    "x": click_x,
                    "y": click_y,
                    "timestamp": mouse_movements[-1]["timestamp"] - random.uniform(50, 200),
                    "duration": random.uniform(50, 400)
                },
                "completionTime": random.uniform(3000, 15000),
                "mouseMovements": mouse_movements,
                "screenSize": {
                    "width": 1920,
                    "height": 1080
                },
                "buttonLocation": {
                    "x": 776,
                    "y": 496.6875,
                    "width": 360,
                    "height": 48
                },
                "windowSize": {
                    "width": 1912,
                    "height": 954
                },
                "isMobile": False
            }
        }

        return solution