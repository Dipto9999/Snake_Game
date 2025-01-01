# Group#: G6
# Student Names: Muntakim Rahman, Tomaz Zlindra

"""
    This program implements a variety of the snake
    game (https://en.wikipedia.org/wiki/Snake_(video_game_genre))

    The model of Inter-Process Communication (IPC) implemented has been changed from message passing to shared-memory.
    This entails a separate thread for the `superloop()` method of the `Game` class, in a producer-consumer problem (with the producer able to act as both a reader and a writer).

    Similar to Lab 5, we are using locks (i.e. mutexes in a dict) to protect read-write access to the memory instead of the `queue`
    from the original design. We are also indicating when there is a new value produced with semaphores (i.e. released by producer, acquired by consumer).
    Access to the "score", "prey", and "move" data fields is protected by critical sections. In other words, a mutex must be acquired for all shared resources,
    except for "game_over", for which we use a binary semaphore (i.e. value = 0 if game not over, 1 otherwise).

    *Note that in this redesign, the prey coordinates are tracked within the `Game` class as well.*
    This is updated with logic in the `Game` class, and read by the `Gui` class to update the Tkinter widgets.

    Note that the `Gui` class read access has been designed to have non-blocking semaphore and blocking mutex acquisition for all data fields.
    If a certain mutex from the dict cannot be acquired (i.e. data being written to when context-switch occurs), it is momentarily skipped in favor of updating the other `Tkinter` widgets.
    The thread behaves similarly if a semaphore cannot be acquired (i.e. no new data has been produced by the game instance).
    This is done through scheduling an update every 100ms to behave similarly as in the original program design (i.e. with the `Tk.after(...)` method). Since the game has a speed of 150 ms,
    these "full" semaphores eliminate the need to update the widget unless needed.

    **IMPORTANT** Tkinter is intended to be single-threaded and we cannot perform Gui updates outside of the main thread. This is problematic since the `Tk.mainloop()` method is blocking
    as long as the gui instance is running. (See The Python Software Foundation. (n.d.). Tkinter - Python interface to TCL/TK. Python Documentation. https://docs.python.org/3/library/tkinter.html#threading-model)
    More is described in the supplementary .pdf report.
"""

import threading

from tkinter import Tk, Canvas, Button
import random, time

class Gui():
    """
        This class takes care of the game's graphic user interface (gui)
        creation and termination.
    """
    def __init__(self):
        """
            The initializer instantiates the main window and
            creates the starting icons for the snake and the prey,
            and displays the initial gamer score.
        """
        #some GUI constants
        scoreTextXLocation = 60
        scoreTextYLocation = 15
        textColour = "white"
        #instantiate and create gui
        self.root = Tk()
        self.canvas = Canvas(self.root, width = WINDOW_WIDTH,
            height = WINDOW_HEIGHT, bg = BACKGROUND_COLOUR)
        self.canvas.pack()
        #create starting game icons for snake and the prey
        self.snakeIcon = self.canvas.create_line(
            (0, 0), (0, 0), fill=ICON_COLOUR, width=SNAKE_ICON_WIDTH)
        self.preyIcon = self.canvas.create_rectangle(
            0, 0, 0, 0, fill=ICON_COLOUR, outline=ICON_COLOUR)
        #display starting score of 0
        self.score = self.canvas.create_text(
            scoreTextXLocation, scoreTextYLocation, fill=textColour,
            text='Your Score: 0', font=("Helvetica","11","bold"))
        #binding the arrow keys to be able to control the snake
        for key in ("Left", "Right", "Up", "Down"):
            self.root.bind(f"<Key-{key}>", game.whenAnArrowKeyIsPressed)
        self.update()

    def update(self) -> None:
        '''
            This method handles the state by trying to retrieve
            data from the game and accordingly taking the corresponding
            action. These include : game_over, move, prey, score.
            Before exiting, this method schedules to call itself after a short delay.

            For general gameplay, non-blocking semaphore acquisition is used to determine whether the
            gui should be updated. In order for these to occur, it must be confirmed that the game is not over.
        '''
        def updateSnake() -> None:
            if game.full["move"].acquire(blocking = False): # Consume New Value
                game.locks["move"].acquire() # Critical Section (Start)
                self.canvas.coords(self.snakeIcon, *[coord for point in game.snakeCoordinates for coord in point])
                game.locks["move"].release() # Critical Section (End)
        def updatePrey() -> None:
            if game.full["prey"].acquire(blocking = False): # Consume New Value
                game.locks["prey"].acquire() # Critical Section (Start)
                self.canvas.coords(self.preyIcon, *game.preyCoordinates)
                game.locks["prey"].release() # Critical Section (End)
        def updateScore() -> None:
            if game.full["score"].acquire(blocking = False): # Consume New Value
                game.locks["score"].acquire() # Critical Section (Start)
                self.canvas.itemconfigure(self.score, text=f"Your Score: {game.score}")
                game.locks["score"].release() # Critical Section (End)

        updateSnake()
        updatePrey()
        updateScore()
        if game.full["game_over"].acquire(blocking = False): # Consume New Value (i.e. Game Over)
            self.gameOver()
        else:
            self.root.after(100, self.update) # Call Function Every 100 ms

    def gameOver(self) -> None:
        """
            This method is used at the end to display a
            game over button.
        """
        gameOverButton = Button(self.canvas, text="Game Over!",
            height = 3, width = 10, font=("Helvetica","14","bold"),
            command=self.root.destroy)
        self.canvas.create_window(200, 100, anchor="nw", window=gameOverButton)

class Game():
    '''
        This class implements most of the game functionalities.
    '''
    def __init__(self):
        """
           This initializer sets the locks and full semaphores for the producer-consumer synchronization problem.
           It also sets the initial snake coordinate list, movement,
           direction, and arranges for the first prey to be created.
        """
        self.locks = {
            "move": threading.Lock(),
            "prey": threading.Lock(),
            "score": threading.Lock(),
        }

        self.full = {
            "game_over": threading.Semaphore(value = 0),
            "move": threading.Semaphore(value = 0),
            "prey": threading.Semaphore(value = 0),
            "score": threading.Semaphore(value = 0),
        }

        #starting length and location of the snake
        #note that it is a list of tuples, each being an
        # (x, y) tuple. Initially its size is 5 tuples.
        self.score: int = 0
        self.snakeCoordinates = [(495, 55), (485, 55), (475, 55),
                                 (465, 55), (455, 55)]
        #initial direction of the snake
        self.direction = "Left"
        self.gameNotOver = True

        self.createNewPrey() # Generate First Prey

    def superloop(self) -> None:
        """
            This method implements a main loop
            of the game. It constantly generates "move"
            tasks to cause the constant movement of the snake.
            Use the SPEED constant to set how often the move tasks
            are generated.
        """
        SPEED = 0.15     #speed of snake updates (sec)
        while self.gameNotOver:
            #complete the method implementation below
            time.sleep(SPEED)
            self.move()

    def whenAnArrowKeyIsPressed(self, e) -> None:
        """
            This method is bound to the arrow keys
            and is called when one of those is clicked.
            It sets the movement direction based on
            the key that was pressed by the gamer.
            Use as is.
        """
        currentDirection = self.direction
        #ignore invalid keys
        if (currentDirection == "Left" and e.keysym == "Right" or
            currentDirection == "Right" and e.keysym == "Left" or
            currentDirection == "Up" and e.keysym == "Down" or
            currentDirection == "Down" and e.keysym == "Up"):
            return
        self.direction = e.keysym

    def move(self) -> None:
        """
            This method implements what is needed to be done
            for the movement of the snake.
            It generates a new snake coordinate.
            If based on this new movement, the prey has been
            captured, it updates the score and also creates a new prey.
            It also calls a corresponding method to check if
            the game should be over.
            The snake coordinates list (representing its length
            and position) should be correctly updated.
        """
        def isCaptured(snakeCoordinates: tuple, preyCoordinates: list) -> bool:
            captureCoordinates = (
                snakeCoordinates[0] - SNAKE_ICON_WIDTH // 2, # x0
                snakeCoordinates[1] - SNAKE_ICON_WIDTH // 2, # y0
                snakeCoordinates[0] + SNAKE_ICON_WIDTH // 2, # x1
                snakeCoordinates[1] + SNAKE_ICON_WIDTH // 2 # y1
            )

            isCaptured: bool = False
            # Checks if Snake Coordinates are in Prey Coordinates (instance where Prey could be much larger than Snake)
            if (captureCoordinates[0] <= preyCoordinates[2] and captureCoordinates[1] <= preyCoordinates[3]) and (captureCoordinates[0] >= preyCoordinates[0] and captureCoordinates[1] >= preyCoordinates[1]): # Snake Point 0 "inside" Prey
                isCaptured = True
            elif (captureCoordinates[2] >= preyCoordinates[0] and captureCoordinates[3] >= preyCoordinates[1]) and (captureCoordinates[2] <= preyCoordinates[2] and captureCoordinates[3] <= preyCoordinates[3]): # Snake Point 1 "inside" Prey
                isCaptured = True
            # Checks if Prey Coordinates are in Snake Coordinates (instance where Snake could be much larger than Prey)
            elif (preyCoordinates[2] >= captureCoordinates[0] and preyCoordinates[3] >= captureCoordinates[1]) and (preyCoordinates[2] <= captureCoordinates[2] and preyCoordinates[3] <= captureCoordinates[3]): # Prey Point 0 "inside" Snake
                isCaptured = True
            elif (preyCoordinates[0] <= captureCoordinates[2] and preyCoordinates[1] <= captureCoordinates[3]) and (preyCoordinates[0] >= captureCoordinates[0] and preyCoordinates[1] >= captureCoordinates[1]): # Prey Point 1 "inside" Snake
                isCaptured = True
            return isCaptured

        def moveSnake(isPreyCaptured: bool, newCoordinates: tuple) -> None:
            self.locks["move"].acquire() # Critical Section (Start)
            if isPreyCaptured:
                self.snakeCoordinates = [*self.snakeCoordinates, newCoordinates] # Append New Snake Head
            else:
                self.snakeCoordinates = [*self.snakeCoordinates[1:], newCoordinates] # Move Snake
            self.locks["move"].release() # Critical Section (End)
            self.full["move"].release() # Produce Value

        def incrementScore() -> None:
            self.locks["score"].acquire() # Critical Section (Start)
            self.score += 1
            self.locks["score"].release() # Critical Section (End)
            self.full["score"].release() # Produce Value

        NewSnakeCoordinates = self.calculateNewCoordinates()

        self.isGameOver(NewSnakeCoordinates)

        preyCaptured = isCaptured(NewSnakeCoordinates, preyCoordinates = gui.canvas.coords(gui.preyIcon))
        moveSnake(isPreyCaptured = preyCaptured, newCoordinates = NewSnakeCoordinates)

        if preyCaptured:
            self.createNewPrey()
            incrementScore()

    def calculateNewCoordinates(self) -> tuple:
        """
            This method calculates and returns the new
            coordinates to be added to the snake
            coordinates list based on the movement
            direction and the current coordinate of
            head of the snake.
            It is used by the move() method.
        """

        lastX, lastY = self.snakeCoordinates[-1] # Read Head Coordinate for Processing (Don't Need Critical Section)

        #complete the method implementation below
        if self.direction == "Left":
            lastX -= SNAKE_ICON_WIDTH
        elif self.direction == "Right":
            lastX += SNAKE_ICON_WIDTH
        elif self.direction == "Up":
            lastY -= SNAKE_ICON_WIDTH
        else:
            lastY += SNAKE_ICON_WIDTH
        return (lastX, lastY)

    def isGameOver(self, snakeCoordinates: tuple) -> None:
        """
            This method checks if the game is over by
            checking if now the snake has passed any wall
            or if it has bit itself.
            If that is the case, it updates the gameNotOver
            field and releases the binary semaphore for the gui.
        """
        x, y = snakeCoordinates
        #complete the method implementation below

        x_collision: bool = (x <= 0) or (x >= WINDOW_WIDTH)
        y_collision: bool = (y <= 0) or (y >= WINDOW_HEIGHT)

        if (x_collision) or (y_collision) or ((x, y) in self.snakeCoordinates[:-1]):
            self.gameNotOver = False
            self.full["game_over"].release() # Produce Value (i.e. Game Over)
        return

    def createNewPrey(self) -> None:
        """
            This methods picks an x and a y randomly as the coordinate
            of the new prey and uses that to calculate the
            coordinates (x - 5, y - 5, x + 5, y + 5). [you need to replace 5 with a constant]
            It then updates the self.preyCoordinates data field with the calculated
            rectangle coordinates as its value. This is used by the
            gui to represent the new prey.
            To make playing the game easier, set the x and y to be THRESHOLD
            away from the walls.
        """
        THRESHOLD = 15

        generatedCoordinates: tuple = (
            random.randint(THRESHOLD, WINDOW_WIDTH - THRESHOLD),  # Generate X Coordinate Threshold Away From Walls
            random.randint(THRESHOLD, WINDOW_HEIGHT - THRESHOLD)  # Generate X Coordinate Threshold Away From Walls
        )

        self.locks["prey"].acquire() # Critical Section (Start)
        self.preyCoordinates = (
            generatedCoordinates[0] - PREY_ICON_WIDTH // 2, # x0
            generatedCoordinates[1] - PREY_ICON_WIDTH // 2, # y0
            generatedCoordinates[0] + PREY_ICON_WIDTH // 2, # x1
            generatedCoordinates[1] + PREY_ICON_WIDTH // 2 # y1
        )
        self.locks["prey"].release() # Critical Section (End)
        self.full["prey"].release() # Produce Value

if __name__ == "__main__":
    #some constants for our GUI
    WINDOW_WIDTH = 500
    WINDOW_HEIGHT = 300
    SNAKE_ICON_WIDTH = 15
    PREY_ICON_WIDTH = 10 # add the specified constant PREY_ICON_WIDTH here

    BACKGROUND_COLOUR = "black" # you may change this colour if you wish
    ICON_COLOUR = "blue"        # you may change this colour if you wish

    game = Game() # instantiate the game object
    gui = Gui() # instantiate the game user interface

    threading.Thread(target = game.superloop, daemon = True).start() # start a thread with the superloop of the game
    gui.root.mainloop() # start the GUI's own event loop