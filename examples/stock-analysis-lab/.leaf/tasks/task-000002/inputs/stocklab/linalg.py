from __future__ import annotations

import math
from typing import Iterable


class LinearAlgebraError(ValueError):
    pass


def dot(left: Iterable[float], right: Iterable[float]) -> float:
    a, b = list(left), list(right)
    if len(a) != len(b):
        raise LinearAlgebraError("dot-product dimensions do not match")
    return math.fsum(x * y for x, y in zip(a, b))


def transpose(matrix: list[list[float]]) -> list[list[float]]:
    if not matrix:
        return []
    width = len(matrix[0])
    if width == 0 or any(len(row) != width for row in matrix):
        raise LinearAlgebraError("matrix must be non-empty and rectangular")
    return [list(column) for column in zip(*matrix)]


def matvec(matrix: list[list[float]], vector: list[float]) -> list[float]:
    return [dot(row, vector) for row in matrix]


def matmul(left: list[list[float]], right: list[list[float]]) -> list[list[float]]:
    columns = transpose(right)
    if left and columns and len(left[0]) != len(columns[0]):
        raise LinearAlgebraError("matrix multiplication dimensions do not match")
    return [[dot(row, column) for column in columns] for row in left]


def solve(matrix: list[list[float]], vector: list[float], *, tolerance: float = 1e-12) -> list[float]:
    size = len(matrix)
    if size == 0 or len(vector) != size or any(len(row) != size for row in matrix):
        raise LinearAlgebraError("solve requires a non-empty square matrix")
    augmented = [list(map(float, row)) + [float(value)] for row, value in zip(matrix, vector)]
    scale = max((abs(value) for row in matrix for value in row), default=1.0)
    threshold = tolerance * max(1.0, scale)
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) <= threshold:
            raise LinearAlgebraError("matrix is singular or numerically unstable")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        divisor = augmented[column][column]
        augmented[column] = [value / divisor for value in augmented[column]]
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor:
                augmented[row] = [
                    current - factor * pivot_value
                    for current, pivot_value in zip(augmented[row], augmented[column])
                ]
    return [augmented[row][-1] for row in range(size)]


def inverse(matrix: list[list[float]]) -> list[list[float]]:
    size = len(matrix)
    columns = [solve(matrix, [1.0 if row == column else 0.0 for row in range(size)]) for column in range(size)]
    return transpose(columns)


def cholesky(matrix: list[list[float]], *, jitter: float = 1e-12, attempts: int = 8) -> list[list[float]]:
    size = len(matrix)
    if size == 0 or any(len(row) != size for row in matrix):
        raise LinearAlgebraError("Cholesky requires a non-empty square matrix")
    if any(abs(matrix[row][column] - matrix[column][row]) > 1e-9 for row in range(size) for column in range(size)):
        raise LinearAlgebraError("Cholesky requires a symmetric matrix")
    for attempt in range(attempts):
        added = 0.0 if attempt == 0 else jitter * (10 ** (attempt - 1))
        lower = [[0.0] * size for _ in range(size)]
        valid = True
        for row in range(size):
            for column in range(row + 1):
                residual = matrix[row][column] + (added if row == column else 0.0)
                residual -= math.fsum(lower[row][k] * lower[column][k] for k in range(column))
                if row == column:
                    if residual <= 0.0:
                        valid = False
                        break
                    lower[row][column] = math.sqrt(residual)
                else:
                    lower[row][column] = residual / lower[column][column]
            if not valid:
                break
        if valid:
            return lower
    raise LinearAlgebraError("matrix is not positive definite after jitter")


def column_means(observations: list[list[float]]) -> list[float]:
    columns = transpose(observations)
    return [math.fsum(column) / len(column) for column in columns]


def covariance_matrix(observations: list[list[float]]) -> list[list[float]]:
    if len(observations) < 2:
        raise LinearAlgebraError("covariance requires at least two observations")
    means = column_means(observations)
    width = len(means)
    return [
        [
            math.fsum((row[i] - means[i]) * (row[j] - means[j]) for row in observations) / (len(observations) - 1)
            for j in range(width)
        ]
        for i in range(width)
    ]


def shrink_covariance(covariance: list[list[float]], intensity: float) -> list[list[float]]:
    if not 0.0 <= intensity <= 1.0:
        raise LinearAlgebraError("shrinkage intensity must be between zero and one")
    size = len(covariance)
    target = math.fsum(covariance[i][i] for i in range(size)) / size
    return [
        [
            (1.0 - intensity) * covariance[i][j] + intensity * (target if i == j else 0.0)
            for j in range(size)
        ]
        for i in range(size)
    ]


def quadratic(vector: list[float], matrix: list[list[float]]) -> float:
    return dot(vector, matvec(matrix, vector))


def project_simplex(values: list[float]) -> list[float]:
    if not values:
        raise LinearAlgebraError("cannot project an empty vector")
    ordered = sorted(values, reverse=True)
    cumulative = 0.0
    rho = 0
    for index, value in enumerate(ordered, start=1):
        cumulative += value
        if value - (cumulative - 1.0) / index > 0.0:
            rho = index
    threshold = (math.fsum(ordered[:rho]) - 1.0) / rho
    projected = [max(value - threshold, 0.0) for value in values]
    total = math.fsum(projected)
    return [value / total for value in projected]
